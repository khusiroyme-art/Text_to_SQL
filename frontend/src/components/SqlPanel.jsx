// Editable on purpose: the generated SQL is a draft, not an oracle. Anything
// typed here still goes through the backend safety layer - an edited query is
// not a trusted query.
export default function SqlPanel({ sql, onChange, onRun, busy }) {
  return (
    <section className="sql-panel">
      <div className="sql-head">
        <h2>SQL</h2>
        <button type="button" onClick={onRun} disabled={busy !== null || !sql.trim()}>
          {busy === "running" ? "Running..." : "Run this SQL"}
        </button>
      </div>
      <textarea
        className="sql"
        value={sql}
        spellCheck={false}
        placeholder="Generated SQL appears here, and you can edit it before running."
        onChange={(e) => onChange(e.target.value)}
      />
    </section>
  );
}
