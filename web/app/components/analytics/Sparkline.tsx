/** Tiny inline SVG line; enough to show shape, not a chart library. */
export function Sparkline({ series, width = 120, height = 32, stroke = "#0a0a0a" }: { series: number[]; width?: number; height?: number; stroke?: string }) {
  if (!series || series.length < 2) return <svg width={width} height={height} aria-hidden />;
  const max = Math.max(...series);
  const min = Math.min(...series);
  const span = max - min || 1;
  const step = width / (series.length - 1);
  const d = series.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function LineChart({ series, labels, height = 220 }: { series: number[]; labels: string[]; height?: number }) {
  const width = 800;
  if (!series || series.length < 2) {
    return (
      <div className="flex items-center justify-center text-sm" style={{ height, color: "var(--muted)" }}>
        Not enough data yet.
      </div>
    );
  }
  const max = Math.max(...series, 1);
  const pad = { l: 40, r: 8, t: 8, b: 24 };
  const w = width - pad.l - pad.r;
  const h = height - pad.t - pad.b;
  const x = (i: number) => pad.l + (i / (series.length - 1)) * w;
  const y = (v: number) => pad.t + h - (v / max) * h;
  const path = series.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${path} L${x(series.length - 1).toFixed(1)},${(pad.t + h).toFixed(1)} L${pad.l},${(pad.t + h).toFixed(1)} Z`;
  const ticks = [0, 0.5, 1].map((f) => ({ v: max * f, y: y(max * f) }));
  const labelEvery = Math.max(1, Math.round(labels.length / 6));
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Metric over time">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={pad.l} x2={width - pad.r} y1={t.y} y2={t.y} stroke="#e5e5e5" />
          <text x={pad.l - 6} y={t.y + 4} fontSize={10} textAnchor="end" fill="#737373">
            {Math.round(t.v).toLocaleString()}
          </text>
        </g>
      ))}
      <path d={area} fill="#0a0a0a" opacity={0.06} />
      <path d={path} fill="none" stroke="#0a0a0a" strokeWidth={2} strokeLinejoin="round" />
      {labels.map((l, i) =>
        i % labelEvery === 0 ? (
          <text key={l} x={x(i)} y={height - 6} fontSize={10} textAnchor="middle" fill="#737373">
            {l.slice(5)}
          </text>
        ) : null,
      )}
    </svg>
  );
}
