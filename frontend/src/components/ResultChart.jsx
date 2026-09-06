import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartSpec } from "../chartSpec.js";

// Categorical slots 1-3, dark-mode steps, validated against this app's chart
// surface (#171a21): lightness band, chroma floor, CVD separation, normal-vision
// floor and 3:1 contrast all pass, on adjacent pairs and all pairs.
// Never extend this by generating a fourth hue - chartSpec caps the series
// count instead.
const SERIES = ["#3987e5", "#d95926", "#199e70"];

const AXIS = "#8b93a7"; // text-secondary: axes are recessive, never a series hue
const GRID = "#2a2f3a";
const SURFACE = "#171a21";

const compact = (v) =>
  typeof v === "number"
    ? Math.abs(v) >= 1000
      ? v.toLocaleString(undefined, { maximumFractionDigits: 1, notation: "compact" })
      : String(Math.round(v * 100) / 100)
    : v;

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tooltip-label">{label}</div>
      {payload.map((entry) => (
        <div key={entry.name} className="tooltip-row">
          {/* The swatch carries identity; the text stays in ink tokens. */}
          <span className="swatch" style={{ background: entry.color }} />
          <span className="tooltip-name">{entry.name}</span>
          <span className="tooltip-value">{compact(entry.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function ResultChart({ result }) {
  const spec = chartSpec(result);
  if (!spec || spec.kind === "none") return null;

  // A single value is a number, not a one-bar bar chart.
  if (spec.kind === "stat") {
    return (
      <section className="chart">
        <div className="stat-tile">
          <span className="stat-label">{spec.label}</span>
          <span className="stat-value">{compact(spec.value)}</span>
        </div>
      </section>
    );
  }

  const axisProps = {
    stroke: AXIS,
    tick: { fill: AXIS, fontSize: 11 },
    tickLine: false,
  };
  // One series needs no legend - the axis title names it. Two or more always do.
  const showLegend = spec.series.length > 1;
  const single = spec.series.length === 1;

  return (
    <section className="chart">
      <div className="chart-head">
        <h2>Chart</h2>
        <span className="muted">
          {spec.kind === "line" ? "Trend over time" : "Comparison by " + spec.xLabel}
        </span>
      </div>
      {spec.note && <p className="note">{spec.note}</p>}
      <div className="chart-body">
        <ResponsiveContainer width="100%" height={280}>
          {spec.kind === "line" ? (
            <LineChart data={spec.data} margin={{ top: 12, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="__label" {...axisProps} />
              <YAxis {...axisProps} tickFormatter={compact} width={56} />
              <Tooltip content={<ChartTooltip />} cursor={{ stroke: AXIS, strokeWidth: 1 }} />
              {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: AXIS }} />}
              {spec.series.map((name, i) => (
                <Line
                  key={name}
                  type="monotone"
                  dataKey={name}
                  stroke={SERIES[i]}
                  strokeWidth={2}
                  // >=8px markers, ringed in the surface so overlaps stay readable.
                  dot={{ r: 4, fill: SERIES[i], stroke: SURFACE, strokeWidth: 2 }}
                  activeDot={{ r: 6, stroke: SURFACE, strokeWidth: 2 }}
                />
              ))}
            </LineChart>
          ) : (
            <BarChart data={spec.data} margin={{ top: 16, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="__label" {...axisProps} interval={0} height={48} angle={-20} textAnchor="end" />
              <YAxis {...axisProps} tickFormatter={compact} width={56} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "#ffffff10" }} />
              {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: AXIS }} />}
              {spec.series.map((name, i) => (
                <Bar
                  key={name}
                  dataKey={name}
                  // One series, one color for every bar. Shading bars by value
                  // would double-encode length as hue and say nothing new.
                  fill={SERIES[i]}
                  // 4px rounded data-end, square against the baseline.
                  radius={[4, 4, 0, 0]}
                  maxBarSize={56}
                >
                  {single && spec.data.length <= 10 && (
                    <LabelList dataKey={name} position="top" fill={AXIS} fontSize={11} formatter={compact} />
                  )}
                </Bar>
              ))}
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}
