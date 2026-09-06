# Text-to-SQL Agent

Natural-language question -> generated SQL (editable) -> executed safely -> result table + optional chart.

**Stack:** Flask backend, React frontend, Claude (Anthropic API) for SQL generation.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Backend skeleton, `POST /query`, DB connector abstraction | done |
| 2 | Schema extraction + DDL formatting + cache | done |
| 3 | Prompt engineering (`build_prompt`) | pending |
| 4 | Safety layer (SELECT-only, blacklist, timeout, LIMIT) | pending |
| 5 | Retry loop on DB error | pending |
| 6 | React frontend | pending |
| 7 | Charts, multi-DB upload, voice input | pending |
| 8 | Deploy | pending |

## Layout

```
backend/
  app.py                  Flask entrypoint
  config.py               env config
  db/
    base.py               DBConnector ABC + QueryResult
    sqlite_connector.py   SQLite (read-only URI mode=ro)
    registry.py           db_id -> connector
  services/
    schema_service.py     introspection cache + CREATE TABLE DDL rendering
    sql_generator.py      NL -> SQL (stubbed until Phase 3)
    safety.py             single chokepoint for every SQL string
    llm_log.py            {prompt, response, latency} JSONL logging
  data/
    seed_demo.py          4-table sales dataset
    demo.sqlite           shipped demo database
frontend/                 React app (Phase 6)
```

## Run

```bash
pip install -r backend/requirements.txt
python backend/data/seed_demo.py     # only needed to re-seed
python -m backend.app                # http://127.0.0.1:5000
```

```bash
curl -X POST http://127.0.0.1:5000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Who are our top spending customers?","db_id":"demo"}'
```

Response shape is always `{ sql, result, error, columns }`.

`GET /schema/<db_id>` returns the cached schema as both prompt-ready DDL and a
`{table: [[col, type], ...]}` mapping.

## Design rules

- Every SQL string passes through `services/safety.py::check()` before execution. No exceptions, no string interpolation into `cursor.execute`.
- SQLite is opened read-only at the driver level (`file:...?mode=ro`) as a backstop beneath the safety layer.
- Schemas are cached per `db_id` and evicted by a cheap fingerprint (SQLite: file mtime + size), so introspection does not run on every request.
- Every LLM call is logged with prompt, response and latency (`services/llm_log.py`).
- `db_id` is a registry key, never a filesystem path from the client.
