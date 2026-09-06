"""SQL generation.

PHASE 1: hardcoded stub, no LLM call. The signature is the one the real
generator will keep, so wiring Claude in during Phase 3 touches this file only.
"""

from dataclasses import dataclass


@dataclass
class Generation:
    sql: str
    #: Filled in from Phase 3 onward: prompt, raw response, latency_ms.
    debug: dict


STUB_SQL = """SELECT c.name AS customer, SUM(oi.quantity * oi.unit_price) AS total_spend
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN order_items oi ON oi.order_id = o.id
GROUP BY c.id, c.name
ORDER BY total_spend DESC"""


def generate_sql(question: str, dialect: str, schema_ddl: str | None = None) -> Generation:
    """Return SQL for a natural-language question.

    Phase 1 ignores every argument and returns a fixed query so the request
    path can be exercised end to end without an API key.
    """
    return Generation(
        sql=STUB_SQL,
        debug={"stub": True, "question": question, "dialect": dialect},
    )
