"""SQLite implementation of DBConnector.

Opened via URI with ``mode=ro`` so the driver itself refuses writes - this is
a hard backstop underneath the SQL safety layer, not a replacement for it.
"""

import os
import sqlite3
from typing import Any, Sequence

from .base import Column, DBConnector, QueryResult, Schema, Table

# Tables SQLite creates for its own bookkeeping; never shown to the LLM.
_INTERNAL_PREFIXES = ("sqlite_",)


class SQLiteConnector(DBConnector):
    dialect = "sqlite"

    def __init__(self, path: str):
        if not os.path.exists(path):
            raise FileNotFoundError(f"SQLite database not found: {path}")
        self.path = os.path.abspath(path)

    def _connect(self, timeout: float) -> sqlite3.Connection:
        # file: URI + mode=ro => read-only handle. Other processes can still
        # write (e.g. a re-seeded demo db), which is why we fingerprint mtime.
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

    def fingerprint(self) -> str:
        """(mtime, size) of the database file - a stat call, not a query.

        Uploaded databases (Phase 7) get a new path anyway, but re-seeding the
        demo file in place still invalidates the cached schema.
        """
        st = os.stat(self.path)
        return f"{st.st_mtime_ns}:{st.st_size}"

    def introspect(self) -> Schema:
        conn = self._connect(timeout=5.0)
        try:
            table_names = [
                r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
                )
                if not r["name"].startswith(_INTERNAL_PREFIXES)
            ]

            tables: list[Table] = []
            for name in table_names:
                # PRAGMA takes an identifier, not a bindable parameter, so the
                # name is quoted rather than interpolated raw. It comes from
                # sqlite_master, never from user input.
                quoted = '"' + name.replace('"', '""') + '"'

                fks: dict[str, str] = {}
                for fk in conn.execute(f"PRAGMA foreign_key_list({quoted})"):
                    target_col = fk["to"] or "id"
                    fks[fk["from"]] = f"{fk['table']}.{target_col}"

                columns = [
                    Column(
                        name=col["name"],
                        type=(col["type"] or "TEXT").upper(),
                        not_null=bool(col["notnull"]),
                        primary_key=bool(col["pk"]),
                        references=fks.get(col["name"]),
                    )
                    for col in conn.execute(f"PRAGMA table_info({quoted})")
                ]
                tables.append(Table(name=name, columns=columns))

            return Schema(dialect=self.dialect, tables=tables, fingerprint=self.fingerprint())
        finally:
            conn.close()
