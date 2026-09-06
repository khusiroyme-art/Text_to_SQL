"""Flask entrypoint.

POST /query -> {sql, result, error, columns}: schema is looked up, Claude
generates the SQL, and every statement is routed through the safety layer
before it reaches the database. The generate/check/execute/repair loop lives
in services/query_service.py; this file only unpacks the request.
"""

import logging

from flask import Flask, jsonify, request
from flask_cors import CORS

from . import config
from .db import registry
from .db.registry import UnknownDatabase
from .services import query_service, schema_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("text2sql.app")


def create_app() -> Flask:
    app = Flask(__name__)
    # The React dev server is a different origin (5173 vs 5000), so the browser
    # blocks its fetches without this. Origins come from config, not "*".
    CORS(app, origins=[o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()])
    registry.bootstrap()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "databases": registry.list_databases()})

    @app.get("/schema/<db_id>")
    def schema(db_id: str):
        """Schema for one database, both as DDL and as a {table: columns} map."""
        try:
            connector = registry.get_connector(db_id)
        except UnknownDatabase as exc:
            return jsonify({"error": str(exc)}), 404
        loaded = schema_service.get_schema(db_id, connector)
        return jsonify(
            {
                "db_id": db_id,
                "dialect": loaded.dialect,
                "ddl": schema_service.format_ddl(loaded),
                "tables": loaded.as_mapping(),
                "error": None,
            }
        )

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

        outcome = query_service.run_query(db_id, connector, question)
        log.info("db=%s question=%r attempts=%s", db_id, question, len(outcome.attempts))
        return _response(
            sql=outcome.sql,
            result=outcome.rows,
            error=outcome.error,
            columns=outcome.columns,
            attempts=len(outcome.attempts),
        )

    @app.post("/execute")
    def execute():
        """Run SQL the user wrote or edited in the browser.

        Same chokepoint as generated SQL: editing a query in a text box does
        not make it trusted.
        """
        payload = request.get_json(silent=True) or {}
        sql = (payload.get("sql") or "").strip()
        db_id = (payload.get("db_id") or "").strip()

        if not sql:
            return _response(error="'sql' is required"), 400
        if not db_id:
            return _response(error="'db_id' is required"), 400

        try:
            connector = registry.get_connector(db_id)
        except UnknownDatabase as exc:
            return _response(error=str(exc)), 404

        outcome = query_service.run_sql(connector, sql)
        return _response(
            sql=outcome.sql,
            result=outcome.rows,
            error=outcome.error,
            columns=outcome.columns,
            attempts=len(outcome.attempts),
        )

    return app


def _response(
    sql: str | None = None,
    result=None,
    error: str | None = None,
    columns=None,
    attempts: int = 0,
):
    """The one response shape the frontend ever has to handle.

    `error` is always present and always the single place to look: a rejected
    query, a dead API key and an exhausted retry budget all land here rather
    than in an HTTP status the client has to branch on.
    """
    return jsonify(
        {"sql": sql, "result": result, "error": error, "columns": columns, "attempts": attempts}
    )


app = create_app()

if __name__ == "__main__":
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.DEBUG)
