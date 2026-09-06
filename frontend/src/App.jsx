import { useCallback, useEffect, useState } from "react";
import { askQuestion, fetchHealth, fetchSchema, runSql } from "./api.js";
import SchemaPanel from "./components/SchemaPanel.jsx";
import ResultTable from "./components/ResultTable.jsx";
import SqlPanel from "./components/SqlPanel.jsx";

const EXAMPLES = [
  "Who are our top spending customers?",
  "What are total sales by product category?",
  "Which orders are still pending?",
  "How many customers signed up per country?",
];

export default function App() {
  const [databases, setDatabases] = useState([]);
  const [dbId, setDbId] = useState("");
  const [schema, setSchema] = useState(null);

  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [attempts, setAttempts] = useState(0);
  const [busy, setBusy] = useState(null); // "asking" | "running" | null

  // Discover which databases the backend has registered, then select the first.
  useEffect(() => {
    fetchHealth()
      .then((health) => {
        setDatabases(health.databases || []);
        setDbId((current) => current || (health.databases || [])[0] || "");
      })
      .catch(() => setError("Cannot reach the backend. Is it running on port 5000?"));
  }, []);

  useEffect(() => {
    if (!dbId) return;
    setSchema(null);
    fetchSchema(dbId)
      .then(setSchema)
      .catch(() => setSchema(null));
  }, [dbId]);

  // One place to absorb a response, because /query and /execute return the
  // same shape and should update the page the same way.
  const absorb = useCallback((response, { keepSql = false } = {}) => {
    setError(response.error || null);
    setAttempts(response.attempts || 0);
    if (!keepSql && response.sql) setSql(response.sql);
    // On failure, clear stale rows rather than leaving a previous answer on
    // screen next to a new error - that reads as if the error were harmless.
    setResult(
      response.error
        ? null
        : { columns: response.columns || [], rows: response.result || [] }
    );
  }, []);

  async function onAsk(event) {
    event.preventDefault();
    if (!question.trim() || !dbId) return;
    setBusy("asking");
    setResult(null);
    setError(null);
    absorb(await askQuestion(question, dbId));
    setBusy(null);
  }

  async function onRunSql() {
    if (!sql.trim() || !dbId) return;
    setBusy("running");
    setError(null);
    // keepSql: the user's text stays exactly as typed. The backend returns a
    // normalised version (aliases expanded, LIMIT appended) and overwriting
    // the box mid-edit would be infuriating.
    absorb(await runSql(sql, dbId), { keepSql: true });
    setBusy(null);
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Text-to-SQL</h1>
          <p className="tagline">Ask in English. Read the SQL. Edit it if it is wrong.</p>
        </div>
        <label className="db-picker">
          Database
          <select value={dbId} onChange={(e) => setDbId(e.target.value)}>
            {databases.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      </header>

      <div className="layout">
        <SchemaPanel schema={schema} />

        <main className="main">
          <form className="ask" onSubmit={onAsk}>
            <input
              type="text"
              value={question}
              placeholder="e.g. Who are our top spending customers?"
              onChange={(e) => setQuestion(e.target.value)}
              disabled={busy !== null}
            />
            <button type="submit" disabled={busy !== null || !question.trim()}>
              {busy === "asking" ? "Thinking..." : "Ask"}
            </button>
          </form>

          <div className="examples">
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                className="chip"
                disabled={busy !== null}
                onClick={() => setQuestion(example)}
              >
                {example}
              </button>
            ))}
          </div>

          {error && (
            <div className="error" role="alert">
              <strong>Error</strong>
              <span>{error}</span>
            </div>
          )}

          {attempts > 1 && !error && (
            <p className="note">
              Took {attempts} attempts &mdash; the first query failed and was repaired
              from the database error.
            </p>
          )}

          <SqlPanel sql={sql} onChange={setSql} onRun={onRunSql} busy={busy} />

          <ResultTable result={result} />
        </main>
      </div>
    </div>
  );
}
