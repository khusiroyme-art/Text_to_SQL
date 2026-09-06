"""The question -> answer pipeline, including the retry loop.

This owns the whole cycle - generate, check, execute, and on failure hand the
database's own error back to the model - so the Flask view stays a view and
the loop can be tested without HTTP.

Why a real loop instead of a prompt instruction ("if the query fails, fix
it"): a prompt cannot be counted, capped, logged, or reasoned about. A loop
can. Every attempt is recorded, the cap is a number, and each failure carries
the stage it failed at.
"""

import logging
from dataclasses import dataclass, field

from .. import config
from ..db.base import DBConnector, QueryTimeout
from . import safety, schema_service, sql_generator

log = logging.getLogger("text2sql.query")


@dataclass
class Attempt:
    """One trip round the loop, successful or not."""

    number: int
    sql: str | None
    #: "generation" | "safety" | "execution" | "ok"
    stage: str
    error: str | None = None


@dataclass
class QueryOutcome:
    sql: str | None = None
    columns: list[str] | None = None
    rows: list | None = None
    error: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    debug: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def run_sql(connector: DBConnector, sql: str) -> QueryOutcome:
    """Check and execute SQL that a *human* wrote or edited.

    No generation and no retry: the user is the author here, so an error is
    something for them to read and fix, not something to paper over with
    another API call. The safety layer applies exactly as it does to generated
    SQL - an edited query is not a trusted query.
    """
    outcome = QueryOutcome()
    try:
        checked_sql = safety.check(sql, dialect=connector.dialect)
    except safety.UnsafeSQL as exc:
        outcome.sql = sql
        outcome.error = f"Rejected by safety layer: {exc}"
        outcome.attempts.append(Attempt(1, sql, "safety", outcome.error))
        return outcome

    outcome.sql = checked_sql
    try:
        result = connector.execute(checked_sql, timeout=safety.DEFAULT_TIMEOUT_SECONDS)
    except QueryTimeout as exc:
        outcome.error = str(exc)
        outcome.attempts.append(Attempt(1, checked_sql, "execution", outcome.error))
        return outcome
    except Exception as exc:
        outcome.error = str(exc)
        outcome.attempts.append(Attempt(1, checked_sql, "execution", outcome.error))
        return outcome

    outcome.columns = result.columns
    outcome.rows = [list(r) for r in result.rows]
    outcome.attempts.append(Attempt(1, checked_sql, "ok"))
    return outcome


def run_query(db_id: str, connector: DBConnector, question: str) -> QueryOutcome:
    """Answer `question` against `connector`, retrying on recoverable errors.

    Never raises for an expected failure: the reason lands in `outcome.error`
    and the caller renders it. A returned outcome always carries the attempt
    trail that produced it.
    """
    schema = schema_service.get_schema(db_id, connector)
    schema_ddl = schema_service.format_ddl(schema)
    dialect = connector.dialect

    outcome = QueryOutcome()
    last_sql: str | None = None
    last_error: str | None = None

    for number in range(1, config.MAX_ATTEMPTS + 1):
        # --- generate ----------------------------------------------------
        try:
            if last_error is None:
                generation = sql_generator.generate_sql(
                    question, dialect=dialect, schema_ddl=schema_ddl
                )
            else:
                log.info("attempt %s: repairing after %r", number, last_error)
                generation = sql_generator.repair_sql(
                    question,
                    dialect=dialect,
                    schema_ddl=schema_ddl,
                    failed_sql=last_sql or "",
                    error_message=last_error,
                )
        except sql_generator.GenerationError as exc:
            # The model is unreachable or refused - retrying the same call
            # buys nothing, so stop here rather than burning the budget.
            outcome.attempts.append(Attempt(number, None, "generation", str(exc)))
            outcome.error = str(exc)
            return outcome

        outcome.debug = generation.debug
        last_sql = generation.sql

        # --- check -------------------------------------------------------
        try:
            checked_sql = safety.check(generation.sql, dialect=dialect)
        except safety.UnsafeSQL as exc:
            # Recoverable: the model wrote the wrong *kind* of statement, and
            # it is worth telling it exactly why we refused.
            reason = f"Rejected by safety layer: {exc}"
            outcome.attempts.append(Attempt(number, generation.sql, "safety", reason))
            last_error = reason
            continue

        last_sql = checked_sql

        # --- execute -----------------------------------------------------
        try:
            result = connector.execute(checked_sql, timeout=safety.DEFAULT_TIMEOUT_SECONDS)
        except QueryTimeout as exc:
            # Not recoverable by rewriting: the same query times out again.
            outcome.attempts.append(Attempt(number, checked_sql, "execution", str(exc)))
            outcome.sql = checked_sql
            outcome.error = str(exc)
            return outcome
        except Exception as exc:
            # The interesting case: "no such column: revenue" is exactly the
            # feedback the model needs, so hand it straight back.
            outcome.attempts.append(Attempt(number, checked_sql, "execution", str(exc)))
            last_error = str(exc)
            continue

        outcome.attempts.append(Attempt(number, checked_sql, "ok"))
        outcome.sql = checked_sql
        outcome.columns = result.columns
        outcome.rows = [list(r) for r in result.rows]
        log.info("answered in %s attempt(s), %s row(s)", number, len(outcome.rows))
        return outcome

    # Budget exhausted - report the last thing that went wrong, not a generic
    # "failed", so the user can see whether it was their question or our SQL.
    outcome.sql = last_sql
    outcome.error = f"Gave up after {config.MAX_ATTEMPTS} attempts. Last error: {last_error}"
    log.warning("exhausted retries for %r: %s", question, last_error)
    return outcome
