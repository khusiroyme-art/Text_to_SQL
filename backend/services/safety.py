"""Safety layer: the single chokepoint every SQL string passes through.

Nothing in this codebase may call ``connector.execute()`` without going
through :func:`check` first.

The design is an **allowlist, not a keyword blacklist**. Blacklists lose:
``SELECT/**/1; DROP TABLE t``, ``sELeCt``, a DROP hidden in a CTE, a comment
that swallows the rest of the statement. So instead of scanning text we parse
with sqlglot and accept exactly one shape - a single SELECT (or set operation)
- rejecting everything else by default. A statement type nobody has thought of
yet fails closed.

Read-only SQLite handles (``mode=ro``) sit underneath this as a second line of
defence, but they only cover SQLite and only cover writes; this layer is what
also stops stacked statements, file access and runaway result sets.
"""

import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, UnsupportedError

log = logging.getLogger("text2sql.safety")


class UnsafeSQL(Exception):
    """Raised when a statement is rejected before it reaches the database."""


DEFAULT_ROW_LIMIT = 500
DEFAULT_TIMEOUT_SECONDS = 5.0

#: The only top-level statements allowed through. A leading CTE parses as a
#: Select; UNION/INTERSECT/EXCEPT parse as SetOperation.
_ALLOWED_ROOTS = (exp.Select, exp.SetOperation)

#: Functions that reach outside the database. SQLite ships or commonly loads
#: all of these, and none of them belong in a generated analytics query.
_BANNED_FUNCTIONS = frozenset(
    {
        "load_extension",
        "readfile",
        "writefile",
        "edit",
        "fts3_tokenizer",
        "pg_read_file",
        "pg_sleep",
        "lo_import",
        "lo_export",
        "sys_exec",
        "sys_eval",
        "load_file",
        "sleep",
        "benchmark",
    }
)


def check(
    sql: str,
    dialect: str = "sqlite",
    row_limit: int = DEFAULT_ROW_LIMIT,
) -> str:
    """Validate and normalize SQL, returning the statement safe to execute.

    Raises :class:`UnsafeSQL` on anything that is not a single read-only
    query. On success the returned SQL always carries a row limit of at most
    ``row_limit``.
    """
    if not sql or not sql.strip():
        raise UnsafeSQL("Empty SQL statement")

    try:
        statements = sqlglot.parse(sql, read=dialect)
    except sqlglot.errors.SqlglotError as exc:
        # Unparseable is unsafe: we cannot reason about what we cannot read.
        #
        # Catch the base class, not ParseError. TokenError is a *sibling* of
        # ParseError, not a subclass, and it is what sqlglot raises for an
        # unterminated quote - which is exactly what prose wrapped around a
        # query produces. Catching only ParseError let it escape as a 500,
        # turning "reject this" into "crash the request".
        raise UnsafeSQL(f"Could not parse SQL: {exc}") from exc

    # Drop the empty trailing statement a lone semicolon leaves behind, so
    # "SELECT 1;" is one statement while "SELECT 1; DROP TABLE t" is two.
    statements = [s for s in statements if s is not None]
    if not statements:
        raise UnsafeSQL("No SQL statement found")
    if len(statements) > 1:
        raise UnsafeSQL(
            f"Only one statement may be executed; got {len(statements)}"
        )

    statement = statements[0]
    if not isinstance(statement, _ALLOWED_ROOTS):
        raise UnsafeSQL(
            f"Only SELECT queries are allowed; got {type(statement).__name__.upper()}"
        )

    _reject_dangerous_nodes(statement)

    limited = _apply_row_limit(statement, row_limit)
    try:
        # We execute the *regenerated* string, so it has to mean exactly what
        # we just validated. By default sqlglot downgrades constructs it cannot
        # render and only logs a warning - e.g. it silently drops the column
        # list from `WITH RECURSIVE x(i) AS ...`, turning a valid query into a
        # broken one. RAISE makes that a rejection instead of a surprise.
        safe_sql = limited.sql(dialect=dialect, unsupported_level=ErrorLevel.RAISE)
    except UnsupportedError as exc:
        raise UnsafeSQL(f"Query uses SQL we cannot safely normalize: {exc}") from exc
    log.debug("safety check passed: %s", safe_sql)
    return safe_sql


def _reject_dangerous_nodes(statement: exp.Expression) -> None:
    """Walk the whole tree - a SELECT can still hide trouble inside it."""
    # exp.Command is sqlglot's escape hatch for statements it passes through
    # verbatim (VACUUM, and anything else it does not model). Never execute one.
    command = statement.find(exp.Command)
    if command is not None:
        raise UnsafeSQL(f"Unsupported statement: {command.sql()}")

    # A write can be nested: e.g. a subquery or a CTE body.
    for node_type, label in (
        (exp.Insert, "INSERT"),
        (exp.Update, "UPDATE"),
        (exp.Delete, "DELETE"),
        (exp.Drop, "DROP"),
        (exp.Create, "CREATE"),
        (exp.Alter, "ALTER"),
        (exp.Pragma, "PRAGMA"),
        (exp.Into, "SELECT ... INTO"),
    ):
        if statement.find(node_type) is not None:
            raise UnsafeSQL(f"{label} is not allowed")

    for func in statement.find_all(exp.Anonymous):
        name = str(func.this).lower()
        if name in _BANNED_FUNCTIONS:
            raise UnsafeSQL(f"Function '{name}' is not allowed")


def _apply_row_limit(statement: exp.Expression, row_limit: int) -> exp.Expression:
    """Guarantee a LIMIT of at most `row_limit`, honouring a smaller one.

    A user who asked for "the top 5 customers" keeps their LIMIT 5; a model
    that emitted no limit, or one larger than ours, gets clamped.
    """
    existing = statement.args.get("limit")
    if existing is not None:
        value = existing.expression
        if isinstance(value, exp.Literal) and value.is_int:
            if int(value.name) <= row_limit:
                return statement
        # A non-literal limit (expression, placeholder) is not something we can
        # compare, so replace it with ours.
    return statement.limit(row_limit)
