"""Safety layer: the single chokepoint every SQL string passes through.

PHASE 1 is a pass-through placeholder so the call site exists from day one and
Phase 4 has exactly one function to fill in (sqlglot parse, SELECT-only check,
keyword blacklist, auto LIMIT, timeout). Nothing in this codebase may call
connector.execute() without going through check().
"""


class UnsafeSQL(Exception):
    """Raised when a statement is rejected before it reaches the database."""


DEFAULT_ROW_LIMIT = 500
DEFAULT_TIMEOUT_SECONDS = 5.0


def check(sql: str, dialect: str = "sqlite") -> str:
    """Validate and normalize SQL, returning the statement safe to execute.

    Phase 4 replaces the body. Raising UnsafeSQL is the only rejection path.
    """
    if not sql or not sql.strip():
        raise UnsafeSQL("Empty SQL statement")
    return sql.strip().rstrip(";")
