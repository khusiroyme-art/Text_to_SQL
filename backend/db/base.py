"""Database connector abstraction.

Every backend (SQLite now; Postgres/MySQL later) implements this same
interface, so nothing above this layer knows which engine it is talking to.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Sequence


class QueryResult:
    """Uniform result container returned by every connector."""

    def __init__(self, columns: list[str], rows: list[Sequence[Any]]):
        self.columns = columns
        self.rows = rows

    def to_dict(self) -> dict:
        return {"columns": self.columns, "rows": [list(r) for r in self.rows]}


@dataclass
class Column:
    name: str
    type: str
    not_null: bool = False
    primary_key: bool = False
    #: "other_table.other_column" when this column is a foreign key.
    references: str | None = None


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)


@dataclass
class Schema:
    """Engine-independent description of a database."""

    dialect: str
    tables: list[Table] = field(default_factory=list)
    #: Changes whenever the underlying database changes; drives cache eviction.
    fingerprint: str = ""

    def as_mapping(self) -> dict[str, list[tuple[str, str]]]:
        """The plain {table: [(col, type), ...]} view asked for in Phase 2."""
        return {t.name: [(c.name, c.type) for c in t.columns] for t in self.tables}


class DBConnector(ABC):
    """Read-only connector interface.

    Implementations must open the underlying database read-only wherever the
    driver supports it. Nothing here accepts a SQL string that has not already
    passed through the safety layer (see backend/services/safety.py).
    """

    #: SQL dialect name handed to the LLM prompt (Phase 3).
    dialect: str = "sql"

    @abstractmethod
    def execute(self, sql: str, params: Sequence[Any] = (), timeout: float = 5.0) -> QueryResult:
        """Run a single read-only statement and return columns + rows."""

    @abstractmethod
    def introspect(self) -> Schema:
        """Read table/column metadata straight from the database."""

    @abstractmethod
    def fingerprint(self) -> str:
        """Cheap token that changes when the schema might have changed.

        Called on every request, so it must not run a full introspection.
        """

    def close(self) -> None:  # pragma: no cover - optional for pooled drivers
        return None
