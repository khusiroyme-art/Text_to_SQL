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
| 7 | Charts, multi-DB upload, voice input | done |
| 8 | Deploy | done |

## Layout

```
Dockerfile                two-stage: Node builds the app, Python runs it
render.yaml               Render blueprint (one web service)
backend/
  app.py                  Flask entrypoint + serves the built frontend
  config.py               env config
  db/
    base.py               DBConnector ABC + QueryResult
    sqlite_connector.py   SQLite (read-only URI mode=ro)
    registry.py           db_id -> connector
  services/
    schema_service.py     introspection cache + CREATE TABLE DDL rendering
    prompts.py            system prompt, rules, few-shot examples
    sql_generator.py      Messages API call, response parsing, logging
    query_service.py      generate -> check -> execute -> repair loop
    safety.py             sqlglot parse + SELECT-only allowlist + row limit
    upload_service.py     validates and registers user-supplied .sqlite files
    llm_log.py            {prompt, response, latency} JSONL logging
  data/
    seed_demo.py          4-table sales dataset
    demo.sqlite           shipped demo database
frontend/
  vite.config.js          dev-server proxy: /api -> 127.0.0.1:5000
  src/
    api.js                every backend call, one response shape
    App.jsx               page state and the ask/run flows
    chartSpec.js          picks bar / line / stat tile / nothing from a result
    useSpeech.js          Web Speech API hook (browser-side only)
    components/           DatabasePicker, SchemaPanel, SqlPanel,
                          ResultChart, ResultTable
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

Open http://localhost:5173. Both servers must run in development: the page is
served by Vite, which proxies `/api/*` to Flask.

To run the production shape locally instead - one process, one port, no Vite:

```bash
cd frontend && npm run build && cd ..
python -m backend.app                # http://127.0.0.1:5000 serves both
```

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/khusiroyme-art/Text_to_SQL)

One click on the button above: Render reads `render.yaml`, builds the
Dockerfile, and asks only for `ANTHROPIC_API_KEY`. Or by hand:

1. Push to GitHub.
2. In Render: **New > Blueprint**, point it at the repo. It reads
   `render.yaml`.
3. Set `ANTHROPIC_API_KEY` when prompted. It is marked `sync: false`, so it
   lives in Render's dashboard and never in the repo.
4. Deploy. `/health` is the health check.

It builds from the `Dockerfile` rather than Render's native Python runtime
because the build needs Node (Vite) *and* Python (Flask) in one step - the
Dockerfile states that dependency instead of relying on whatever a base image
happens to include. The same image runs anywhere:

```bash
docker build -t text-to-sql .
docker run -p 5000:5000 -e ANTHROPIC_API_KEY=sk-ant-... text-to-sql
# or, keeping the key out of your shell history:
docker run -p 5000:5000 --env-file .env text-to-sql
```

`--env-file` is read by Docker itself, not by the app, so a `.env` file works
for a container run even though nothing loads one for a local `python -m
backend.app`.

**Uploaded databases are ephemeral.** They are written to the container's
local disk and are lost on every restart and redeploy - which on Render's free
tier includes spinning down when idle. They are meant for a single session,
not for storage. Attaching a persistent disk is the fix if that ever matters.

`FLASK_DEBUG` defaults to off. Flask's debugger executes arbitrary code sent
from a browser, so it is opt-in for local work rather than opt-out in
production.

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

`POST /databases` takes a multipart `file` and registers an uploaded SQLite
database, returning `{db_id, label, tables}`. `GET /health` lists what is
registered, which is what the database picker renders.

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
- In production one Flask process serves both the built React app and the API, so there is no CORS, no second service, and no origin to keep in sync.
- Flask's built-in static route is switched off deliberately: it would claim `/<path:filename>` and 404 every client-side route. The SPA view owns those paths instead - but a missing `.js` or `.css` still 404s rather than being answered with the HTML shell, because masking a build error as a MIME error helps nobody.
- An upload is checked cheapest-first: extension, then size, then SQLite's magic header, then an actual read-only introspection. It is stored under a generated id, never the client's filename, so a traversal attempt is just a odd-looking label.
- Chart type is derived from the data, not chosen: a single value is a stat tile (never a one-bar bar chart), a date-like x axis is a line, categories are bars, and 25+ rows stay a table. Numeric `id` columns are labels, not measures.
- Chart colours are the first three slots of a validated categorical palette, checked against this app's surface for lightness, chroma, colour-blind separation and contrast. A fourth measure is never given a generated hue - it stays in the table.
- Voice input is entirely browser-side (Web Speech API). No audio reaches the backend, and the button is hidden where the API is missing rather than shown broken.
- Editing the SQL in the browser does not make it trusted: `/execute` runs it through the same `safety.check()` as generated SQL.
- The frontend never branches on HTTP status. Every call resolves to `{sql, result, error, columns, attempts}` and `error` is the only failure channel - even a network outage is synthesised into that shape.
- The generated SQL is shown and editable because it is a draft, not an oracle; the schema sits on screen because the first question about a wrong answer is always whether the model knew about that column.
- Prompt *text* lives in `services/prompts.py`, prompt *plumbing* in `services/sql_generator.py`, so the wording can be rewritten without touching an API call.
- The system prompt (rules + schema DDL + few-shots) is stable per database and marked cacheable; the question rides in `messages` after the cache breakpoint. `cache_read_input_tokens` is logged so a silent cache miss is visible.
- The prompt is told the same row limit `safety.DEFAULT_ROW_LIMIT` actually enforces - one constant, no drift.
