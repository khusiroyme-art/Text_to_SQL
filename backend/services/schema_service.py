"""Schema extraction, caching, and DDL formatting for prompt injection.

CREATE TABLE-style DDL is what goes into the prompt: it is the format LLMs see
most during training, it carries types/keys/relationships in fewer tokens than
a JSON dump, and it reads the same way the model is expected to write.
"""

import logging
import threading

from ..db.base import DBConnector, Schema

log = logging.getLogger("text2sql.schema")

# db_id -> (fingerprint, Schema). Guarded because Flask serves requests from
# multiple threads.
_CACHE: dict[str, tuple[str, Schema]] = {}
_LOCK = threading.Lock()


def get_schema(db_id: str, connector: DBConnector) -> Schema:
    """Return the schema for db_id, introspecting only when it has changed."""
    current = connector.fingerprint()
    with _LOCK:
        cached = _CACHE.get(db_id)
        if cached and cached[0] == current:
            return cached[1]

    # Introspect outside the lock: it touches the database and we would rather
    # do the work twice on a race than serialise every cold request.
    log.info("introspecting schema for db_id=%s (fingerprint=%s)", db_id, current)
    schema = connector.introspect()
    with _LOCK:
        _CACHE[db_id] = (schema.fingerprint or current, schema)
    return schema


def invalidate(db_id: str | None = None) -> None:
    """Drop one cached schema, or all of them."""
    with _LOCK:
        if db_id is None:
            _CACHE.clear()
        else:
            _CACHE.pop(db_id, None)


def format_ddl(schema: Schema) -> str:
    """Render the schema as compact CREATE TABLE statements.

    Example output:

        CREATE TABLE orders (
          id INTEGER PRIMARY KEY,
          customer_id INTEGER NOT NULL REFERENCES customers(id),
          order_date TEXT NOT NULL
        );
    """
    blocks: list[str] = []
    for table in schema.tables:
        lines = []
        for col in table.columns:
            parts = [col.name, col.type]
            if col.primary_key:
                parts.append("PRIMARY KEY")
            elif col.not_null:
                # PRIMARY KEY already implies NOT NULL; don't spend tokens twice.
                parts.append("NOT NULL")
            if col.references:
                ref_table, ref_col = col.references.split(".", 1)
                parts.append(f"REFERENCES {ref_table}({ref_col})")
            lines.append("  " + " ".join(parts))
        blocks.append(f"CREATE TABLE {table.name} (\n" + ",\n".join(lines) + "\n);")
    return "\n\n".join(blocks)
