"""Structured logging for LLM calls: {prompt, response, latency}.

Used from Phase 3 onward; defined now so no call site has an excuse to skip it.
Writes one JSON object per line to backend/logs/llm.jsonl and mirrors a short
line to the app logger.
"""

import json
import logging
import os
import time
from contextlib import contextmanager

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_PATH = os.path.join(LOG_DIR, "llm.jsonl")

log = logging.getLogger("text2sql.llm")


@contextmanager
def log_call(kind: str, prompt: str):
    """Wrap an LLM call; set record['response'] inside the block."""
    record: dict = {"kind": kind, "prompt": prompt, "response": None}
    started = time.perf_counter()
    try:
        yield record
    finally:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        log.info("llm %s latency=%sms", kind, record["latency_ms"])
