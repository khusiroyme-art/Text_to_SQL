"""Flask entrypoint.

In production this one process serves both halves: the built React app as
static files and the JSON API beneath it, so there is no CORS and no second
service to deploy.

POST /query -> {sql, result, error, columns}: schema is looked up, Claude
generates the SQL, and every statement is routed through the safety layer
before it reaches the database. The generate/check/execute/repair loop lives
in services/query_service.py; this file only unpacks the request.
"""

import logging
import os

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import NotFound
from flask_cors import CORS

from . import config
from .db import registry
from .db.registry import UnknownDatabase
from .services import query_service, schema_service, upload_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("text2sql.app")


def create_app() -> Flask:
    # static_folder is deliberately off. Flask's built-in static route would
    # claim "/<path:filename>" and answer 404 for anything that is not a real
    # file - which is every client-side route. The spa() view below owns those
    # paths instead, so a deep link reaches the app rather than an error page.
    has_frontend = os.path.isdir(config.FRONTEND_DIST)
    app = Flask(__name__, static_folder=None)
    # The React dev server is a different origin (5173 vs 5000), so the browser
    # blocks its fetches without this. Origins come from config, not "*".
    CORS(app, origins=[o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()])
    # Refuse an oversized body at the server, before it is buffered. The
    # upload service checks the size again for a friendlier message; this is
    # the hard stop that does not depend on our code running first.
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_UPLOAD_BYTES
    registry.bootstrap()

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "databases": registry.list_databases(),
                "details": registry.describe_databases(),
            }
        )

    @app.post("/databases")
    def upload_database():
        """Register a user-supplied SQLite file and return its summary."""
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return jsonify({"error": "No file was uploaded (field name: 'file')"}), 400
        try:
            summary = upload_service.save_upload(uploaded)
        except upload_service.UploadRejected as exc:
            log.warning("upload rejected: %s", exc)
            return jsonify({"error": str(exc)}), 400
        return jsonify({**summary, "error": None}), 201

    @app.get("/schema/<db_id>")
    def schema(db_id: str):
        """Schema for one database, both as DDL and as a {table: columns} map."""
        try:
            connector = registry.get_connector(db_id)
        except UnknownDatabase as exc:
            return jsonify({"error": str(exc)}), 404
        loaded = schema_service.get_schema(db_id, connector)
        uploaded = any(
            d["db_id"] == db_id and d["uploaded"] for d in registry.describe_databases()
        )
        return jsonify(
            {
                "db_id": db_id,
                "uploaded": uploaded,
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

    @app.errorhandler(413)
    def too_large(_exc):
        """MAX_CONTENT_LENGTH aborts before any view runs, so answer it here."""
        limit_mb = config.MAX_UPLOAD_BYTES / (1024 * 1024)
        return jsonify({"error": f"File is larger than the {limit_mb:.0f} MB limit"}), 413

    if has_frontend:

        @app.get("/")
        @app.get("/<path:path>")
        def spa(path: str = ""):
            """Serve the built React app, falling back to index.html.

            Registered last and GET-only, so it can never shadow an API route:
            Werkzeug matches the specific rules (/health, /schema/<id>) ahead
            of this catch-all, and /query and /execute are POST.
            """
            if path:
                try:
                    # send_from_directory refuses to escape the directory, so
                    # a traversal in the URL is its problem, not ours.
                    return send_from_directory(config.FRONTEND_DIST, path)
                except NotFound:
                    # A missing file that looks like an asset stays a 404.
                    # Answering with the HTML shell instead would turn a build
                    # problem into a baffling MIME error in the console.
                    if "." in path.rsplit("/", 1)[-1]:
                        raise
            # Everything else is a client-side route: hand back the shell.
            return send_from_directory(config.FRONTEND_DIST, "index.html")

    else:
        log.warning(
            "no built frontend at %s - serving the API only. Run `npm run build` in frontend/.",
            config.FRONTEND_DIST,
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
    # Development entrypoint only. Production runs gunicorn against
    # `backend.app:app` - see render.yaml.
    app.run(host=config.FLASK_HOST, port=config.PORT, debug=config.DEBUG)
