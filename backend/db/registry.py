"""Maps a db_id from the request to a concrete connector instance.

Phase 7 will add uploaded .sqlite files keyed by session; the lookup contract
stays the same so callers never change.
"""

import os

from .base import DBConnector
from .sqlite_connector import SQLiteConnector

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

# db_id -> factory. Explicit registration keeps db_id from being a file path
# the client can point anywhere it likes.
_REGISTRY: dict[str, DBConnector] = {}


class UnknownDatabase(Exception):
    pass


def register_sqlite(db_id: str, path: str) -> None:
    _REGISTRY[db_id] = SQLiteConnector(path)


def get_connector(db_id: str) -> DBConnector:
    if db_id not in _REGISTRY:
        raise UnknownDatabase(f"Unknown db_id '{db_id}'. Known: {sorted(_REGISTRY) or 'none'}")
    return _REGISTRY[db_id]


def list_databases() -> list[str]:
    return sorted(_REGISTRY)


def bootstrap() -> None:
    """Register the databases that ship with the repo."""
    demo = os.path.join(DATA_DIR, "demo.sqlite")
    if os.path.exists(demo):
        register_sqlite("demo", demo)
