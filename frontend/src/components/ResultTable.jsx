export default function ResultTable({ result }) {
  if (!result) return null;

  const { columns, rows } = result;
  if (!rows.length) {
    return <p className="note">Query ran successfully and returned no rows.</p>;
  }

  return (
    <section className="results">
      <div className="results-head">
        <h2>Result</h2>
        <span className="muted">
          {rows.length} row{rows.length === 1 ? "" : "s"}
        </span>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  // NULL is not the same as an empty string, and a table that
                  // renders both as blank hides real data problems.
                  <td key={j} className={cell === null ? "null" : ""}>
                    {cell === null ? "NULL" : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
