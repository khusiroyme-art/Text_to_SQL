"""Prompt construction for SQL generation.

Everything about *what we say to the model* lives in this file. Call logic
(retries, logging, API params) lives in sql_generator.py, so the prompt can be
rewritten without touching a single API call.

Notes from the langchain-ai/text-to-sql-agent reference, and where we differ:

* Their system prompt templates the dialect and a `top_k` row limit, tells the
  model to double-check its query, and forbids DML. We keep all four ideas.
* They let the model *discover* the schema through tools (list tables, then
  inspect). We inject the full CREATE TABLE DDL up front instead: one round
  trip instead of three, and the model cannot "forget" to look at a table.
* Their retry is prompt-only ("if you get an error, rewrite the query"). We
  make it a real capped loop in Phase 5 - a prompt instruction cannot be
  counted, logged, or bounded.
* They ship no few-shot examples. We do, because format compliance (bare SQL,
  no fences, no prose) is far more reliable when demonstrated than described.
"""

from dataclasses import dataclass

# The few-shot examples deliberately use a *different* toy schema from any real
# database. They teach output format and query shape; using the live schema
# here would invite the model to copy example answers instead of reading the
# DDL it was given.
FEW_SHOT_SCHEMA = """CREATE TABLE authors (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  country TEXT NOT NULL
);

CREATE TABLE books (
  id INTEGER PRIMARY KEY,
  author_id INTEGER NOT NULL REFERENCES authors(id),
  title TEXT NOT NULL,
  genre TEXT NOT NULL,
  published_year INTEGER NOT NULL,
  copies_sold INTEGER NOT NULL
);"""

#: (question, sql) pairs covering: single table, filter + sort, join,
#: aggregation over a join, aggregation with HAVING.
DEFAULT_FEW_SHOTS: list[tuple[str, str]] = [
    (
        "List every genre we publish.",
        "SELECT DISTINCT genre FROM books ORDER BY genre;",
    ),
    (
        "Which books published after 2010 sold more than 50000 copies? Show the best sellers first.",
        "SELECT title, published_year, copies_sold\n"
        "FROM books\n"
        "WHERE published_year > 2010 AND copies_sold > 50000\n"
        "ORDER BY copies_sold DESC;",
    ),
    (
        "Show each book with its author's name.",
        "SELECT b.title, a.name AS author\n"
        "FROM books b\n"
        "JOIN authors a ON a.id = b.author_id\n"
        "ORDER BY b.title;",
    ),
    (
        "What are total copies sold per country?",
        "SELECT a.country, SUM(b.copies_sold) AS total_copies_sold\n"
        "FROM books b\n"
        "JOIN authors a ON a.id = b.author_id\n"
        "GROUP BY a.country\n"
        "ORDER BY total_copies_sold DESC;",
    ),
    (
        "Which authors have written more than 3 books?",
        "SELECT a.name, COUNT(*) AS book_count\n"
        "FROM authors a\n"
        "JOIN books b ON b.author_id = a.id\n"
        "GROUP BY a.id, a.name\n"
        "HAVING COUNT(*) > 3\n"
        "ORDER BY book_count DESC;",
    ),
]

SYSTEM_TEMPLATE = """You are a careful SQL analyst. You translate a user's question into exactly one {dialect} query.

# Database schema

{schema_ddl}

# Rules

1. Output ONLY the SQL query. No prose, no explanation, no markdown code fences, no backticks, no trailing commentary.
2. Read-only queries only. Emit exactly one SELECT statement (a leading WITH clause is fine). Never emit DDL or DML: no INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, ATTACH or PRAGMA.
3. Use only tables and columns that appear in the schema above. Never invent a name. If the question cannot be answered from this schema, return exactly: SELECT 'question cannot be answered from this schema' AS error
4. Join through the declared foreign keys rather than guessing at matching columns.
5. Write valid {dialect} - use that dialect's own functions for dates, strings and casting.
6. Unless the user asks for a specific number of rows, do not add your own LIMIT; the application appends a row limit of {row_limit}.
7. Give computed columns a readable alias (for example SUM(quantity * unit_price) AS total_revenue).
8. Double-check the query against the schema before answering: every table exists, every column belongs to the table it is qualified with, and every non-aggregated selected column appears in GROUP BY.

# Examples

These examples use a different database. Copy their output format, not their tables.

{few_shot_schema}
{few_shot_block}"""

REPAIR_TEMPLATE = """The previous query failed against the database.

Original question:
{question}

Failed SQL:
{failed_sql}

Database error:
{error_message}

Fix the SQL and return ONLY the corrected query - no prose, no markdown fences. \
It must still be a single read-only {dialect} SELECT statement that uses only the \
tables and columns in the schema you were given."""


@dataclass
class Prompt:
    """Exactly what gets sent to the Messages API."""

    system: str
    messages: list[dict]

    def as_text(self) -> str:
        """Flat rendering used for the debug log."""
        rendered = [f"[system]\n{self.system}"]
        for m in self.messages:
            rendered.append(f"[{m['role']}]\n{m['content']}")
        return "\n\n".join(rendered)


def _render_few_shots(few_shots: list[tuple[str, str]]) -> str:
    return "\n".join(f"\nQ: {q}\nA: {sql}" for q, sql in few_shots)


def build_prompt(
    schema: str,
    question: str,
    few_shots: list[tuple[str, str]] | None = None,
    dialect: str = "sqlite",
    row_limit: int = 500,
) -> Prompt:
    """Build the initial question -> SQL prompt.

    `schema` is the CREATE TABLE DDL from schema_service.format_ddl().
    Swap the wording here freely; sql_generator never inspects the result.
    """
    shots = DEFAULT_FEW_SHOTS if few_shots is None else few_shots
    system = SYSTEM_TEMPLATE.format(
        dialect=dialect,
        schema_ddl=schema,
        row_limit=row_limit,
        few_shot_schema=FEW_SHOT_SCHEMA,
        few_shot_block=_render_few_shots(shots),
    )
    return Prompt(system=system, messages=[{"role": "user", "content": question}])


def build_repair_prompt(
    schema: str,
    question: str,
    failed_sql: str,
    error_message: str,
    few_shots: list[tuple[str, str]] | None = None,
    dialect: str = "sqlite",
    row_limit: int = 500,
) -> Prompt:
    """Build the Phase 5 retry prompt: same system prompt, new user turn.

    Reusing the identical system string keeps the schema and rules in front of
    the model and keeps the cached prefix intact across attempts.
    """
    base = build_prompt(schema, question, few_shots, dialect, row_limit)
    repair = REPAIR_TEMPLATE.format(
        question=question,
        failed_sql=failed_sql,
        error_message=error_message,
        dialect=dialect,
    )
    return Prompt(system=base.system, messages=[{"role": "user", "content": repair}])
