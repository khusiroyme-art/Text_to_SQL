"""SQL generation: natural-language question -> one SELECT statement.

Split of responsibilities:

* prompts.py  - every word we send to the model.
* this file   - the API call, response parsing, and logging around it.

The system prompt (rules + schema DDL + few-shot examples) is stable for a
given database while the question changes on every request, so the system
block is marked cacheable and the question stays in `messages`. That is the
prefix-cache layout: stable content first, volatile content last.
"""

import logging
import re
from dataclasses import dataclass, field

import anthropic

from .. import config
from . import llm_log, prompts, safety

log = logging.getLogger("text2sql.generator")


class GenerationError(Exception):
    """The model did not produce usable SQL (bad key, API failure, refusal)."""


@dataclass
class Generation:
    sql: str
    #: prompt/response/latency/token counts - surfaced for the debug panel.
    debug: dict = field(default_factory=dict)


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Build the client once, on first use - not at import time.

    Importing this module must stay free of side effects so the app can boot
    (and serve /health, /schema) without an API key configured.
    """
    global _client
    if _client is None:
        if not config.ANTHROPIC_API_KEY:
            raise GenerationError(
                "ANTHROPIC_API_KEY is not set - copy .env.example and export it."
            )
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


# Belt and braces: rule 1 forbids fences, but a stray ```sql block would turn
# into a syntax error at the database rather than something we can explain.
_FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE)


def _extract_sql(text: str) -> str:
    sql = _FENCE.sub("", text.strip()).strip()
    if not sql:
        raise GenerationError("Model returned an empty response")
    return sql


def _complete(prompt: prompts.Prompt, kind: str) -> tuple[str, dict]:
    """Send one prompt, return (text, debug). All API concerns live here."""
    client = _get_client()

    with llm_log.log_call(kind, prompt.as_text()) as record:
        try:
            response = client.beta.messages.create(
                model=config.ANTHROPIC_MODEL,
                max_tokens=config.MAX_TOKENS,
                # Stable prefix: rules + schema + examples. Volatile question
                # goes in messages, after the breakpoint.
                system=[
                    {
                        "type": "text",
                        "text": prompt.system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=prompt.messages,
                thinking={"type": "adaptive"},
                output_config={"effort": config.EFFORT},
                # Safety classifiers can decline a request (HTTP 200, not an
                # error); "default" re-runs it server-side on Anthropic's
                # recommended substitute instead of handing us a dead end.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise GenerationError("Anthropic rejected the API key") from exc
        except anthropic.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after", "60")
            raise GenerationError(f"Rate limited by Anthropic; retry in {retry_after}s") from exc
        except anthropic.APIStatusError as exc:
            raise GenerationError(f"Anthropic API error ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise GenerationError(f"Could not reach the Anthropic API: {exc}") from exc

        # Check stop_reason before touching content: a refusal can carry an
        # empty content list, and thinking blocks are not text blocks.
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None)
            raise GenerationError(f"Request was declined by the model (category={category})")

        text = "".join(b.text for b in response.content if b.type == "text")
        record["response"] = text
        usage = response.usage
        debug = {
            "model": response.model,
            "stop_reason": response.stop_reason,
            "request_id": response._request_id,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        }
        record.update(debug)

    debug["latency_ms"] = record["latency_ms"]
    debug["prompt"] = prompt.as_text()
    debug["raw_response"] = text
    return text, debug


def generate_sql(question: str, dialect: str, schema_ddl: str | None = None) -> Generation:
    """Turn a natural-language question into SQL for `dialect`.

    `schema_ddl` is the CREATE TABLE rendering from schema_service.format_ddl().
    Raises GenerationError; the caller turns that into the response `error`.
    """
    if not schema_ddl:
        raise GenerationError("No schema available for this database")

    prompt = prompts.build_prompt(
        schema=schema_ddl,
        question=question,
        dialect=dialect,
        # One source of truth: the prompt promises the same limit the safety
        # layer actually appends in Phase 4.
        row_limit=safety.DEFAULT_ROW_LIMIT,
    )
    text, debug = _complete(prompt, kind="generate")
    sql = _extract_sql(text)
    log.info("generated sql in %sms: %r", debug["latency_ms"], sql)
    return Generation(sql=sql, debug=debug)


def repair_sql(
    question: str,
    dialect: str,
    schema_ddl: str,
    failed_sql: str,
    error_message: str,
) -> Generation:
    """Second (and later) attempt: show the model its own failure and the error.

    The system prompt is byte-identical to the one build_prompt produced, so
    the schema and rules stay in front of the model and the cached prefix
    survives across attempts - only the user turn changes.
    """
    prompt = prompts.build_repair_prompt(
        schema=schema_ddl,
        question=question,
        failed_sql=failed_sql,
        error_message=error_message,
        dialect=dialect,
        row_limit=safety.DEFAULT_ROW_LIMIT,
    )
    text, debug = _complete(prompt, kind="repair")
    sql = _extract_sql(text)
    log.info("repaired sql in %sms: %r", debug["latency_ms"], sql)
    return Generation(sql=sql, debug=debug)
