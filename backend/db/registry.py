"""Maps a db_id from the request to a concrete connector instance.

The registry is the reason `db_id` is safe to accept from a client: it is a
lookup key in this dict, never a path. An unknown key is an error, so there is
no request that can make the app open a file nobody registered.

Uploaded databases (Phase 7) register here alongside the shipped demo, so
every caller above this layer stays identical whether the database came from
the repo or from a browser.
"""

import os
import threading

from .base import DBConnector
from .sqlite_connector import SQLiteConnector

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


class UnknownDatabase(Exception):
    pass


class _Entry:
    """A registered database: its connector plus how to describe it."""

    def __init__(self, connector: DBConnector, label: str, uploaded: bool):
        self.connector = connector
        self.label = label
        self.uploaded = uploaded


# db_id -> _Entry. Guarded because Flask serves requests from multiple threads
# and uploads mutate this at runtime, not just at boot.
_REGISTRY: dict[str, _Entry] = {}
_LOCK = threading.Lock()


def register_sqlite(db_id: str, path: str, label: str | None = None, uploaded: bool = True) -> None:
    """Register a SQLite file. Constructing the connector validates the path."""
    entry = _Entry(SQLiteConnector(path), label or db_id, uploaded)
    with _LOCK:
        _REGISTRY[db_id] = entry


def get_connector(db_id: str) -> DBConnector:
    with _LOCK:
        entry = _REGISTRY.get(db_id)
    if entry is None:
        raise UnknownDatabase(f"Unknown db_id '{db_id}'. Known: {sorted(_REGISTRY) or 'none'}")
    return entry.connector


def list_databases() -> list[str]:
    with _LOCK:
        return sorted(_REGISTRY)


def describe_databases() -> list[dict]:
    """What the database picker needs: the id, a display label, and origin.

    Sorted so the shipped demo is always first and uploads follow in name
    order - a picker whose contents jump around between requests is worse than
    one that is merely alphabetical.
    """
    with _LOCK:
        entries = list(_REGISTRY.items())
    entries.sort(key=lambda kv: (kv[1].uploaded, kv[1].label.lower()))
    return [
        {"db_id": db_id, "label": entry.label, "uploaded": entry.uploaded}
        for db_id, entry in entries
    ]


def bootstrap() -> None:
    """Register the databases that ship with the repo."""
    demo = os.path.join(DATA_DIR, "demo.sqlite")
    if os.path.exists(demo):
        register_sqlite("demo", demo, label="demo", uploaded=False)
