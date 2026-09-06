// The schema is shown because the model is only as good as the tables it was
// given: when an answer looks wrong, the first question is always whether it
// knew about that column - and this panel is the answer.
export default function SchemaPanel({ schema }) {
  if (!schema || schema.error) {
    return (
      <aside className="schema">
        <h2>Schema</h2>
        <p className="muted">{schema?.error || "Loading..."}</p>
      </aside>
    );
  }

  const tables = Object.entries(schema.tables || {});
  return (
    <aside className="schema">
      <h2>
        Schema <span className="muted">({schema.dialect})</span>
      </h2>
      {tables.map(([table, columns]) => (
        <details key={table} open>
          <summary>{table}</summary>
          <ul>
            {columns.map(([name, type]) => (
              <li key={name}>
                <span className="col">{name}</span>
                <span className="type">{type}</span>
              </li>
            ))}
          </ul>
        </details>
      ))}
    </aside>
  );
}
