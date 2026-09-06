"""SQLite implementation of DBConnector.

Opened via URI with ``mode=ro`` so the driver itself refuses writes — this is
a hard backstop underneath the SQL safety layer, not a replacement for it.
"""

import os
import sqlite3
from typing import Any, Sequence

from .base import DBConnector, QueryResult


class SQLiteConnector(DBConnector):
    dialect = "sqlite"

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"SQLite database not found: {path}")
        self.path = os.path.abspath(path)

    def _connect(self, timeout: float) -> sqlite3.Connection:
        # file: URI + mode=ro => read-only handle. immutable=0 so we still see
        # writes made by other processes (e.g. a re-seeded demo db).
        uri = f"file:{self.path.replace(os.sep, '/')}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
        conn.row_factory = sqlite3.Row
        return conn

    def execute(self, sql: str, params: Sequence[Any] = (), timeout: float = 5.0) -> QueryResult:
        conn = self._connect(timeout)
        try:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            columns = [d[0] for d in cur.description] if cur.description else []
            return QueryResult(columns, [tuple(r) for r in rows])
        finally:
            conn.close()

    def introspect(self) -> dict[str, list[tuple[str, str]]]:
        # Phase 2 fills this in (plus DDL formatting and caching).
        raise NotImplementedError("Schema introspection lands in Phase 2")
