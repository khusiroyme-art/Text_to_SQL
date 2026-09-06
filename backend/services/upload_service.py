"""Accepting a user-supplied SQLite file and registering it as a database.

An upload is the least trusted thing this app touches, so the checks here are
deliberately paranoid and ordered cheapest-first:

1. Size is capped before the bytes are ever read into memory.
2. The file must start with SQLite's magic header - an extension proves
   nothing, and this is the check that rejects a renamed .exe.
3. The stored filename is a generated id, never the client's filename. That
   is what stops ``../../etc/passwd`` and friends: the client's name is only
   ever used as a display label.
4. It must actually open and introspect read-only before we register it. A
   file that survives all four is a real database we can query, not just
   plausible bytes.
"""

import logging
import os
import re
import uuid

from .. import config
from ..db import registry
from ..db.sqlite_connector import SQLiteConnector

log = logging.getLogger("text2sql.upload")

#: Every SQLite 3 database begins with this. 16 bytes, including the NUL.
SQLITE_MAGIC = b"SQLite format 3\x00"

ALLOWED_EXTENSIONS = frozenset({".sqlite", ".sqlite3", ".db"})


class UploadRejected(Exception):
    """The uploaded file is not something we are willing to register."""


def _safe_label(filename: str) -> str:
    """A human-readable label derived from the client's filename.

    Used for display only - never as a path. Anything outside a conservative
    character set is dropped rather than escaped, because there is no reason
    for a database label to contain anything else.
    """
    stem = os.path.splitext(os.path.basename(filename or ""))[0]
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", stem).strip()
    return cleaned[:40] or "uploaded database"


def save_upload(file_storage) -> dict:
    """Validate and register an uploaded SQLite file.

    `file_storage` is a Werkzeug FileStorage. Returns the new database's
    summary; raises UploadRejected with a reason the user can act on.
    """
    filename = file_storage.filename or ""
    extension = os.path.splitext(filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadRejected(
            f"Expected a SQLite file ({', '.join(sorted(ALLOWED_EXTENSIONS))}), got '{extension or 'no extension'}'"
        )

    # Size first: seek to the end rather than reading, so an oversized file
    # costs a seek instead of memory.
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size == 0:
        raise UploadRejected("File is empty")
    if size > config.MAX_UPLOAD_BYTES:
        limit_mb = config.MAX_UPLOAD_BYTES / (1024 * 1024)
        raise UploadRejected(f"File is larger than the {limit_mb:.0f} MB limit")

    header = file_storage.stream.read(len(SQLITE_MAGIC))
    file_storage.stream.seek(0)
    if header != SQLITE_MAGIC:
        # A .sqlite extension is a claim, not evidence.
        raise UploadRejected("That is not a SQLite database file")

    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    db_id = f"up_{uuid.uuid4().hex[:12]}"
    # The id is the filename. The client's filename never touches the path.
    path = os.path.join(config.UPLOAD_DIR, f"{db_id}.sqlite")
    file_storage.save(path)

    # Final gate: prove it is queryable before anyone can select it. If this
    # fails we delete the file rather than leave an unusable upload on disk.
    try:
        connector = SQLiteConnector(path)
        schema = connector.introspect()
    except Exception as exc:
        _remove(path)
        raise UploadRejected(f"Could not read that database: {exc}") from exc

    if not schema.tables:
        _remove(path)
        raise UploadRejected("That database has no tables to query")

    label = _safe_label(filename)
    registry.register_sqlite(db_id, path, label=label)
    log.info("registered upload db_id=%s label=%r tables=%s", db_id, label, len(schema.tables))

    return {
        "db_id": db_id,
        "label": label,
        "tables": [t.name for t in schema.tables],
        "size_bytes": size,
    }


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:  # pragma: no cover - best effort cleanup
        log.warning("could not delete rejected upload at %s", path)
