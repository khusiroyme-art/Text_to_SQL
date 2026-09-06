// Deciding what (if anything) to draw for an arbitrary result set.
//
// The result of a generated query has no schema we control, so the chart type
// is derived from the data rather than chosen by the user. The rules follow
// the "is it even a chart?" question first - a single number is a stat tile,
// not a one-bar bar chart, and thirty rows are a table.

const DATEISH = /^\d{4}(-\d{2}(-\d{2})?)?$/; // 2026, 2026-09, 2026-09-06

// Above this, bars stop being comparable and the table is the better read.
const MAX_PLOTTABLE_ROWS = 25;
// The validated categorical palette seats three series safely. A fourth is
// never a generated hue - the extra measures stay in the table.
const MAX_SERIES = 3;

const isNumber = (v) => typeof v === "number" && Number.isFinite(v);

// A numeric id is a label that happens to be stored as an integer; summing or
// plotting it is meaningless.
const isIdentifier = (name) => /^id$|_id$|^.*_?key$/i.test(name);

/**
 * @returns null (draw nothing), or a spec describing what to render.
 */
export function chartSpec(result) {
  if (!result) return null;
  const { columns = [], rows = [] } = result;
  if (!columns.length || !rows.length) return null;

  const numericCols = [];
  const labelCols = [];
  columns.forEach((name, index) => {
    const values = rows.map((r) => r[index]).filter((v) => v !== null);
    if (!values.length) return;
    if (values.every(isNumber) && !isIdentifier(name)) numericCols.push({ name, index });
    else labelCols.push({ name, index });
  });

  if (!numericCols.length) {
    return { kind: "none", reason: "No numeric column to plot." };
  }

  // One row, one measure: the number *is* the chart.
  if (rows.length === 1 && numericCols.length === 1) {
    const { name, index } = numericCols[0];
    return { kind: "stat", label: name, value: rows[0][index] };
  }

  if (rows.length > MAX_PLOTTABLE_ROWS) {
    return {
      kind: "none",
      reason: `${rows.length} rows read better as a table than as a chart.`,
    };
  }

  // Without a label column, the x axis would be the row number - which tells
  // the reader nothing they cannot already see in the table.
  if (!labelCols.length) {
    return { kind: "none", reason: "No category or date column to plot against." };
  }

  const label = labelCols[0];
  const series = numericCols.slice(0, MAX_SERIES);
  const dropped = numericCols.length - series.length;

  // Dates on the x axis mean the job is "trend over time", which is a line.
  const labelValues = rows.map((r) => r[label.index]);
  const temporal = labelValues.every((v) => typeof v === "string" && DATEISH.test(v));

  // Recharts wants row objects keyed by name, not positional arrays.
  const data = rows.map((row) => {
    const point = { __label: String(row[label.index] ?? "NULL") };
    series.forEach(({ name, index }) => {
      point[name] = row[index];
    });
    return point;
  });

  return {
    kind: temporal ? "line" : "bar",
    xLabel: label.name,
    series: series.map((s) => s.name),
    data,
    note: dropped > 0 ? `Plotting the first ${MAX_SERIES} measures; ${dropped} more are in the table.` : null,
  };
}
