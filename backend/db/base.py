"""Database connector abstraction.

Every backend (SQLite now; Postgres/MySQL later) implements this same
interface, so nothing above this layer knows which engine it is talking to.
"""

from abc import ABC, abstractmethod
from typing import Any, Sequence


class QueryResult:
    """Uniform result container returned by every connector."""

    def __init__(self, columns: list[str], rows: list[Sequence[Any]]):
        self.columns = columns
        self.rows = rows

    def to_dict(self) -> dict:
        return {"columns": self.columns, "rows": [list(r) for r in self.rows]}


class DBConnector(ABC):
    """Read-only connector interface.

    Implementations must open the underlying database read-only wherever the
    driver supports it. Nothing here accepts a SQL string that has not already
    passed through the safety layer (see backend/services/safety.py).
    """

    #: SQL dialect name handed to the LLM prompt later (Phase 3).
    dialect: str = "sql"

    @abstractmethod
    def execute(self, sql: str, params: Sequence[Any] = (), timeout: float = 5.0) -> QueryResult:
        """Run a single read-only statement and return columns + rows."""

    @abstractmethod
    def introspect(self) -> dict[str, list[tuple[str, str]]]:
        """Return {table_name: [(column_name, column_type), ...]}."""

    def close(self) -> None:  # pragma: no cover - optional for pooled drivers
        return None
