import { useId } from "react";

/** Столбчатый график с подписанными осями (E39-32): без подписей осей графики на странице не показываем. */
export interface Series {
  name: string;
  color: string;
  values: (number | null)[];
}

export function BarChart({
  title,
  xLabel,
  yLabel,
  categories,
  series,
  max,
  target,
  format,
}: {
  title: string;
  xLabel: string;
  yLabel: string;
  categories: string[];
  series: Series[];
  max: number;
  /** Горизонтальная линия цели. */
  target?: { value: number; label: string };
  format: (v: number) => string;
}) {
  const id = useId();
  const W = 520;
  const H = 260;
  const L = 56;
  const R = 12;
  const T = 16;
  const B = 56;
  const pw = W - L - R;
  const ph = H - T - B;
  const y = (v: number) => T + ph - (Math.min(v, max) / max) * ph;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((k) => k * max);
  const gw = pw / categories.length;
  const bw = Math.min(40, (gw * 0.7) / series.length);
  return (
    <figure className="flex flex-col gap-2" data-testid="chart">
      <figcaption id={id} className="text-14 font-semibold">
        {title}
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={id} className="w-full max-w-xl">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="stroke-hairline" strokeWidth={1} />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="fill-muted" fontSize={11}>
              {format(t)}
            </text>
          </g>
        ))}
        {categories.map((c, ci) => {
          const x0 = L + ci * gw + (gw - bw * series.length) / 2;
          return (
            <g key={c}>
              {series.map((s, si) => {
                const v = s.values[ci];
                if (v === null || v === undefined) return null;
                return (
                  <g key={s.name}>
                    <rect x={x0 + si * bw} y={y(v)} width={bw - 4} height={Math.max(0, T + ph - y(v))} rx={3} fill={s.color} />
                    <text x={x0 + si * bw + (bw - 4) / 2} y={y(v) - 4} textAnchor="middle" className="fill-ink" fontSize={11}>
                      {format(v)}
                    </text>
                  </g>
                );
              })}
              <text x={L + ci * gw + gw / 2} y={T + ph + 16} textAnchor="middle" className="fill-ink" fontSize={12}>
                {c}
              </text>
            </g>
          );
        })}
        {target && (
          <g>
            <line x1={L} x2={W - R} y1={y(target.value)} y2={y(target.value)} className="stroke-muted" strokeDasharray="5 4" strokeWidth={1.5} />
            <text x={W - R} y={y(target.value) - 4} textAnchor="end" className="fill-muted" fontSize={11}>
              {target.label}
            </text>
          </g>
        )}
        <line x1={L} x2={L} y1={T} y2={T + ph} className="stroke-muted" />
        <line x1={L} x2={W - R} y1={T + ph} y2={T + ph} className="stroke-muted" />
        <text x={L + pw / 2} y={H - 8} textAnchor="middle" className="fill-muted" fontSize={12} data-testid="x-label">
          {xLabel}
        </text>
        <text transform={`translate(14 ${T + ph / 2}) rotate(-90)`} textAnchor="middle" className="fill-muted" fontSize={12} data-testid="y-label">
          {yLabel}
        </text>
      </svg>
      {series.length > 1 && (
        <ul className="flex flex-wrap gap-3 text-12 text-muted">
          {series.map((s) => (
            <li key={s.name} className="flex items-center gap-1.5">
              <span className="inline-block h-3 w-3 rounded-sm" style={{ background: s.color }} />
              {s.name}
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
