# Text-to-SQL Agent

Natural-language question -> generated SQL (editable) -> executed safely -> result table + optional chart.

**Stack:** Flask backend, React frontend, Claude (Anthropic API) for SQL generation.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 1 | Backend skeleton, `POST /query`, DB connector abstraction | done |
| 2 | Schema extraction + DDL formatting + cache | done |
| 3 | Prompt engineering (`build_prompt`) + live Claude call | done |
| 4 | Safety layer (SELECT-only, allowlist, timeout, LIMIT) | done |
| 5 | Retry loop on DB error | done |
| 6 | React frontend | done |
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
    safety.py             sqlglot parse + SELECT-only allowlist + row limit
    llm_log.py            {prompt, response, latency} JSONL logging
  data/
    seed_demo.py          4-table sales dataset
    demo.sqlite           shipped demo database
frontend/
  vite.config.js          dev-server proxy: /api -> 127.0.0.1:5000
  src/
    api.js                every backend call, one response shape
    App.jsx               page state and the ask/run flows
    components/           SchemaPanel, SqlPanel, ResultTable
    styles.css
```

## Run

Backend:

```bash
pip install -r backend/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # see .env.example
python backend/data/seed_demo.py     # only needed to re-seed
python -m backend.app                # http://127.0.0.1:5000
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Open http://localhost:5173. Both servers must run: the page is served by Vite,
which proxies `/api/*` to Flask.

```bash
curl -X POST http://127.0.0.1:5000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Who are our top spending customers?","db_id":"demo"}'
```

Response shape is always `{ sql, result, error, columns, attempts }`. `error` is the single place to look: a rejected query, a dead API key and an exhausted retry budget all land there.

`GET /schema/<db_id>` returns the cached schema as both prompt-ready DDL and a
`{table: [[col, type], ...]}` mapping.

`POST /execute` takes `{sql, db_id}` and runs SQL the user wrote or edited in
the browser. It shares the safety layer but skips generation and retry: the
user is the author, so an error is theirs to read and fix.

## Design rules

- Every SQL string passes through `services/safety.py::check()` before execution. No exceptions, no string interpolation into `cursor.execute`.
- The safety layer is an **allowlist, not a keyword blacklist**: sqlglot parses the statement and only a single top-level SELECT (or UNION/INTERSECT/EXCEPT) is accepted. Stacked statements, comment tricks and casing games all fail on the parse tree rather than on a regex, and an unmodelled statement type fails closed.
- `check()` executes the SQL it *regenerated*, so generation runs at `ErrorLevel.RAISE`: if sqlglot cannot render a construct faithfully it is rejected instead of quietly rewritten.
- Results are capped at `DEFAULT_ROW_LIMIT` (500). A smaller LIMIT the user asked for is preserved; a larger or non-literal one is clamped.
- The retry loop is a real capped loop in `services/query_service.py`, not a prompt instruction ("if it fails, fix it"). A loop can be counted, capped and logged; a sentence cannot. The database's own error text is what goes back to the model.
- Not every failure is worth retrying: a timeout re-runs identically and an unreachable API will not answer, so both return immediately. A bad column name or a rejected statement gets another attempt.
- `timeout` is a real wall-clock budget, not sqlite3's busy-lock timeout: a progress handler interrupts the statement and raises `QueryTimeout`. An unbounded recursive CTE is a legal SELECT, so this is the only thing that stops one.
- SQLite is opened read-only at the driver level (`file:...?mode=ro`) as a backstop beneath the safety layer.
- Schemas are cached per `db_id` and evicted by a cheap fingerprint (SQLite: file mtime + size), so introspection does not run on every request.
- Every LLM call is logged with prompt, response and latency (`services/llm_log.py`).
- `db_id` is a registry key, never a filesystem path from the client.
- Editing the SQL in the browser does not make it trusted: `/execute` runs it through the same `safety.check()` as generated SQL.
- The frontend never branches on HTTP status. Every call resolves to `{sql, result, error, columns, attempts}` and `error` is the only failure channel - even a network outage is synthesised into that shape.
- The generated SQL is shown and editable because it is a draft, not an oracle; the schema sits on screen because the first question about a wrong answer is always whether the model knew about that column.
- Prompt *text* lives in `services/prompts.py`, prompt *plumbing* in `services/sql_generator.py`, so the wording can be rewritten without touching an API call.
- The system prompt (rules + schema DDL + few-shots) is stable per database and marked cacheable; the question rides in `messages` after the cache breakpoint. `cache_read_input_tokens` is logged so a silent cache miss is visible.
- The prompt is told the same row limit `safety.DEFAULT_ROW_LIMIT` actually enforces - one constant, no drift.
