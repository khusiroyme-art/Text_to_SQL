import { useCallback, useEffect, useState } from "react";
import { askQuestion, fetchHealth, fetchSchema, runSql } from "./api.js";
import { useSpeech } from "./useSpeech.js";
import DatabasePicker from "./components/DatabasePicker.jsx";
import SchemaPanel from "./components/SchemaPanel.jsx";
import ResultChart from "./components/ResultChart.jsx";
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

  const speech = useSpeech(setQuestion);

  // Refresh the database list. Called at boot and after every upload, so the
  // picker is always the backend's view rather than a local guess.
  const refreshDatabases = useCallback(async (selectId) => {
    try {
      const health = await fetchHealth();
      const details = health.details || [];
      setDatabases(details);
      setDbId((current) => selectId || current || details[0]?.db_id || "");
    } catch {
      setError("Cannot reach the backend. Is it running on port 5000?");
    }
  }, []);

  useEffect(() => {
    refreshDatabases();
  }, [refreshDatabases]);

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

  // A new database invalidates the previous answer: the SQL referenced tables
  // that may not exist here, and leaving the old rows on screen next to a new
  // database name is the kind of thing that gets misread as a result.
  function onSelectDatabase(nextId) {
    setDbId(nextId);
    setResult(null);
    setSql("");
    setError(null);
    setAttempts(0);
  }

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Text-to-SQL</h1>
          <p className="tagline">Ask in English. Read the SQL. Edit it if it is wrong.</p>
        </div>
        <DatabasePicker
          databases={databases}
          dbId={dbId}
          disabled={busy !== null}
          onSelect={onSelectDatabase}
          onUploaded={(newId) => {
            onSelectDatabase(newId);
            refreshDatabases(newId);
          }}
        />
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
            {/* Hidden rather than disabled where unsupported: a permanently
                dead button is worse than no button. */}
            {speech.supported && (
              <button
                type="button"
                className={speech.listening ? "mic listening" : "mic"}
                onClick={speech.toggle}
                disabled={busy !== null}
                title={speech.listening ? "Stop listening" : "Ask by voice"}
                aria-label={speech.listening ? "Stop listening" : "Ask by voice"}
              >
                {speech.listening ? "Listening..." : "Speak"}
              </button>
            )}
            <button type="submit" disabled={busy !== null || !question.trim()}>
              {busy === "asking" ? "Thinking..." : "Ask"}
            </button>
          </form>

          {speech.error && <p className="note">{speech.error}</p>}

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

          <ResultChart result={result} />
          <ResultTable result={result} />
        </main>
      </div>
    </div>
  );
}
