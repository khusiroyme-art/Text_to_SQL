"""Flask entrypoint.

PHASE 1 scope: POST /query -> {sql, result, error, columns}, SQL generation
stubbed, execution routed through the (currently pass-through) safety layer.
"""

import logging

from flask import Flask, jsonify, request

from . import config
from .db import registry
from .db.registry import UnknownDatabase
from .services import safety
from .services.sql_generator import generate_sql

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("text2sql.app")


def create_app() -> Flask:
    app = Flask(__name__)
    registry.bootstrap()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "databases": registry.list_databases()})

    @app.post("/query")
    def query():
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        db_id = (payload.get("db_id") or "").strip()

        if not question:
            return _response(error="'question' is required"), 400
        if not db_id:
            return _response(error="'db_id' is required"), 400

        try:
            connector = registry.get_connector(db_id)
        except UnknownDatabase as exc:
            return _response(error=str(exc)), 404

        generation = generate_sql(question, dialect=connector.dialect)
        sql = generation.sql
        log.info("db=%s question=%r -> sql=%r", db_id, question, sql)

        try:
            checked_sql = safety.check(sql, dialect=connector.dialect)
        except safety.UnsafeSQL as exc:
            return _response(sql=sql, error=f"Rejected by safety layer: {exc}"), 400

        try:
            result = connector.execute(checked_sql, timeout=safety.DEFAULT_TIMEOUT_SECONDS)
        except Exception as exc:  # Phase 5 turns this into the retry loop.
            log.warning("execution failed: %s", exc)
            return _response(sql=checked_sql, error=str(exc)), 200

        return _response(sql=checked_sql, columns=result.columns, result=result.to_dict()["rows"])

    return app


def _response(sql: str | None = None, result=None, error: str | None = None, columns=None):
    """The one response shape the frontend ever has to handle."""
    return jsonify({"sql": sql, "result": result, "error": error, "columns": columns})


app = create_app()

if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.DEBUG)
