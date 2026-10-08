import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { Lbl, MeterBar, clamp, dotsText } from "./primitives";

/* Графики v2 (доска docs/design/v2/screens/v2_components.html). SVG без библиотек, цвета — var(--токен). */

const MONO = "\"JetBrains Mono Variable\", \"JetBrains Mono\", ui-monospace, monospace";

/** Ломаная-спарклайн по значениям (масштаб по min/max). */
function sparkPath(values: number[], w: number, h: number, pad = 2): string {
  if (values.length < 2) return "";
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - pad - ((v - lo) / span) * (h - pad * 2);
      return `${i ? "L" : "M"}${round(x)} ${round(y)}`;
    })
    .join("");
}

const round = (n: number) => Math.round(n * 10) / 10;

/** Плитка метрики `.tile`: метка, крупное число, под ним спарклайн, полоса или подпись. */
export function MetricTile({
  label,
  value,
  trend,
  progress,
  hint,
  info,
  className,
}: {
  label: string;
  value: ReactNode;
  /** Значения для спарклайна (от старых к новым). */
  trend?: number[];
  /** 0–100: полоса под числом («Место»). */
  progress?: number;
  hint?: ReactNode;
  /** Значок ⓘ рядом с подписью. */
  info?: ReactNode;
  className?: string;
}) {
  const d = trend ? sparkPath(trend, 120, 36) : "";
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 rounded-xl border border-hairline bg-card p-3", className)}>
      <span className="flex items-center gap-1">
        <Lbl>{label}</Lbl>
        {info}
      </span>
      <span className="font-mono text-24 leading-[1.1] font-semibold">{value}</span>
      {d && (
        <svg width="100%" height="28" viewBox="0 0 120 36" preserveAspectRatio="none" aria-hidden>
          <path d={d} fill="none" stroke="var(--brand)" strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
        </svg>
      )}
      {progress !== undefined && <MeterBar value={progress} label={label} />}
      {hint && <span className="num text-11 text-muted">{hint}</span>}
    </div>
  );
}

/* ---------- SkillConstellation ---------- */

export interface ConstellationNode {
  name: string;
  /** 0–4: размер узла и точки доверия. */
  level: number;
  /** confirmed — сплошной, claimed — пунктир, adjacent — смежный (светлый). */
  state?: "confirmed" | "claimed" | "adjacent";
}

/* Места узлов как в макете (viewBox 100 20 520 190): самый сильный — слева, слабые — справа. */
const SLOTS: [number, number][] = [
  [200, 110],
  [360, 62],
  [330, 165],
  [510, 112],
  [480, 188],
  [560, 52],
  [440, 132],
  [250, 182],
  [270, 48],
  [590, 168],
];
const LINKS: [number, number][] = [
  [0, 1],
  [0, 2],
  [1, 2],
  [1, 3],
  [2, 4],
  [3, 4],
  [3, 5],
  [2, 6],
  [0, 7],
  [0, 8],
  [4, 9],
];
const STARS = "M130 40h0M140 190h0M610 50h0M590 150h0M280 205h0M440 22h0M150 120h0M570 200h0";

/** Созвездие навыков: узлы по силе, связи, подписи и точки доверия. До 10 узлов, остальные отбрасываются. */
export function SkillConstellation({ nodes, className, label }: { nodes: ConstellationNode[]; className?: string; label?: string }) {
  const order = [...nodes]
    .map((n, i) => ({ ...n, i, state: n.state ?? "confirmed" }))
    .sort((a, b) => rank(b) - rank(a) || a.i - b.i)
    .slice(0, SLOTS.length);
  const r = (n: (typeof order)[number]) => (n.state === "adjacent" ? 9 : n.state === "claimed" ? 14 : 10 + clamp(n.level, 0, 4) * 3);
  const aria = label ?? `Созвездие навыков: ${order.map((n) => n.name).join(", ")}`;
  return (
    <svg viewBox="100 20 520 190" width="100%" role="img" aria-label={aria} fontFamily={MONO} className={className}>
      <path d={STARS} stroke="var(--tint-200)" strokeWidth="4" strokeLinecap="round" />
      <g stroke="var(--brand)" strokeWidth="1.5" fill="none">
        {LINKS.filter(([a, b]) => a < order.length && b < order.length).map(([a, b]) => {
          const weak = order[a].state !== "confirmed" || order[b].state !== "confirmed";
          return (
            <path
              key={`${a}-${b}`}
              d={`M${SLOTS[a][0]} ${SLOTS[a][1]}L${SLOTS[b][0]} ${SLOTS[b][1]}`}
              opacity={weak ? 0.25 : 0.6}
              strokeDasharray={order[a].state === "claimed" || order[b].state === "claimed" ? "4 4" : undefined}
            />
          );
        })}
      </g>
      {order.map((n, k) => {
        const [x, y] = SLOTS[k];
        const rad = r(n);
        return (
          <g key={n.name} data-state={n.state}>
            {n.state === "confirmed" && <circle cx={x} cy={y} r={rad + 10} fill="var(--tint-100)" opacity=".8" />}
            {n.state === "confirmed" ? (
              <circle cx={x} cy={y} r={rad} fill="var(--brand)" opacity={n.level >= 3 ? 1 : 0.78} />
            ) : (
              <circle
                cx={x}
                cy={y}
                r={rad}
                fill="var(--card)"
                stroke={n.state === "claimed" ? "var(--brand)" : "var(--tint-200)"}
                strokeWidth="1.5"
                strokeDasharray={n.state === "claimed" ? "3 3" : undefined}
              />
            )}
            <text x={x + rad + 16} y={y - 4} fontSize="13" fontWeight="600" fill={n.state === "adjacent" ? "var(--muted)" : "var(--ink)"}>
              {n.name}
            </text>
            {n.state !== "adjacent" && (
              <text x={x + rad + 16} y={y + 12} fontSize="10" fontWeight="600" fill="var(--brand-fg)" letterSpacing="1">
                {dotsText(n.state === "claimed" ? 0 : n.level)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function rank(n: { level: number; state: string }): number {
  return (n.state === "confirmed" ? 10 : n.state === "claimed" ? 5 : 0) + n.level;
}

/* ---------- ScatterPlot ---------- */

export interface ScatterPoint {
  /** 0–100 по оси X (сила). */
  x: number;
  /** 0–100 по оси Y (ожидания, нормированные). */
  y: number;
}

/** «Где ты среди своих»: точки категории, вертикальный порог, точка «ты». Оси 0–100. */
export function ScatterPlot({
  points,
  you,
  threshold,
  yLabel = "ожидания, ₽",
  youLabel = "ты",
  label,
  className,
}: {
  points: ScatterPoint[];
  you?: ScatterPoint;
  threshold?: { x: number; label: string };
  yLabel?: string;
  youLabel?: string;
  label: string;
  className?: string;
}) {
  const X = (v: number) => round(30 + (clamp(v) / 100) * 320);
  const Y = (v: number) => round(160 - (clamp(v) / 100) * 140);
  const dots = points.map((p) => `M${X(p.x)} ${Y(p.y)}h0`).join("");
  return (
    <svg viewBox="0 0 360 180" width="100%" role="img" aria-label={label} fontFamily={MONO} className={cn("max-h-[250px]", className)}>
      <path d="M30 160H350M30 160V14" stroke="var(--hairline)" strokeWidth="1" fill="none" />
      {dots && <path d={dots} stroke="var(--brand-mid)" strokeWidth="6" strokeLinecap="round" />}
      {threshold && (
        <>
          <path d={`M${X(threshold.x)} 20V160`} stroke="var(--brand)" strokeWidth="1.5" strokeDasharray="4 4" />
          <text x={X(threshold.x) + 4} y="26" fontSize="12" fill="var(--brand-fg)" fontWeight="600">
            {threshold.label}
          </text>
        </>
      )}
      {you && (
        <g data-you>
          <circle cx={X(you.x)} cy={Y(you.y)} r="12" fill="var(--tint-100)" />
          <circle cx={X(you.x)} cy={Y(you.y)} r="6" fill="var(--brand)" />
          <text x={X(you.x)} y={Y(you.y) - 18} fontSize="13" fontWeight="600" fill="var(--brand-fg)" textAnchor="middle">
            {youLabel}
          </text>
        </g>
      )}
      <g fontSize="12" fill="var(--muted)">
        <text x="30" y="174">0</text>
        <text x="186" y="174">50</text>
        <text x="338" y="174">100</text>
        <text x="34" y="12">{yLabel}</text>
      </g>
    </svg>
  );
}

/* ---------- ActivityHeatmap ---------- */

// В тёмной теме шкала светлеет к максимуму (tint-200 там серый, brand-deep сливается с фоном).
const HEAT = ["bg-tint-100", "bg-tint-200 dark:bg-brand-deep", "bg-brand-mid dark:bg-brand", "bg-brand dark:bg-brand-mid", "bg-brand-deep dark:bg-ink"] as const;

/** Уровень 0–4 для значения относительно максимума. */
export function heatLevel(v: number, max: number): number {
  if (v <= 0 || max <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((v / max) * 4)));
}

/** Тепловая карта по дням `.hm`: столбцы — недели, 7 строк — дни. `values` — по дням от старых к новым. */
export function ActivityHeatmap({
  values,
  cell = 10,
  label,
  className,
}: {
  values: number[];
  cell?: number;
  label: string;
  className?: string;
}) {
  const max = Math.max(0, ...values);
  return (
    <div
      role="img"
      aria-label={label}
      className={cn("grid grid-flow-col gap-[3px]", className)}
      style={{ gridTemplateRows: `repeat(7, ${cell}px)`, gridAutoColumns: `${cell}px` }}
    >
      {values.map((v, i) => {
        const lvl = heatLevel(v, max);
        return <i key={i} data-level={lvl} className={cn("block rounded-[2px]", HEAT[lvl])} />;
      })}
    </div>
  );
}

/* ---------- GradeScale ---------- */

export interface GradeBand {
  label: string;
  /** Нижняя граница полосы, 0–100. */
  from: number;
}

export const DEFAULT_GRADE_BANDS: GradeBand[] = [
  { label: "до Junior", from: 0 },
  { label: "Junior", from: 30 },
  { label: "Middle", from: 55 },
  { label: "Senior", from: 80 },
];

const BAND_FILL = ["var(--hairline)", "var(--tint-200)", "var(--brand-mid)", "var(--brand)"];
const BAND_TEXT = ["var(--muted)", "var(--chip-fg)", "var(--brand-deep)", "var(--on-brand)"];

/** Шкала грейда: полосы грейдов, пороги, маркер результата и погрешность `±error`. */
export function GradeScale({
  value,
  bands = DEFAULT_GRADE_BANDS,
  error,
  compact,
  label,
  className,
}: {
  value: number;
  bands?: GradeBand[];
  error?: number;
  /** Мини-шкала для узкой карточки (как на доске компонентов): полосы и маркер, без подписей. */
  compact?: boolean;
  label?: string;
  className?: string;
}) {
  const X = (v: number) => round(20 + (clamp(v) / 100) * 1200);
  const v = clamp(value);
  const aria = label ?? `Шкала грейда: ${bands.slice(1).map((b) => `${b.label} от ${b.from}`).join(", ")}. Результат ${Math.round(v)}`;
  if (compact) {
    const x = (t: number) => round(2 + (clamp(t) / 100) * 296);
    return (
      <svg viewBox="0 0 300 60" width="100%" role="img" aria-label={aria} fontFamily={MONO} className={className}>
        {bands.map((b, i) => {
          const x0 = x(b.from) + (i ? 2 : 0);
          const x1 = i + 1 < bands.length ? x(bands[i + 1].from) - 2 : x(100);
          const k = Math.min(i, BAND_FILL.length - 1) + Math.max(0, BAND_FILL.length - bands.length);
          return <rect key={b.label} x={x0} y="24" width={Math.max(0, x1 - x0)} height="14" rx="3" fill={BAND_FILL[k]} />;
        })}
        <path d={`M${x(v)} 40V12`} stroke="var(--signal)" strokeWidth="2" />
        <text x={x(v)} y="9" fontSize="11" fontWeight="700" fill="var(--ink)" textAnchor="middle">
          {Math.round(v)}
        </text>
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 1240 120" width="100%" role="img" aria-label={aria} fontFamily={MONO} className={className}>
      {bands.map((b, i) => {
        const x0 = X(b.from) + (i ? 2 : 0);
        const x1 = (i + 1 < bands.length ? X(bands[i + 1].from) : X(100)) - (i + 1 < bands.length ? 2 : 0);
        const k = Math.min(i, BAND_FILL.length - 1) + Math.max(0, BAND_FILL.length - bands.length);
        return (
          <g key={b.label}>
            <rect x={x0} y="40" width={Math.max(0, x1 - x0)} height="22" rx="4" fill={BAND_FILL[k]} />
            <text x={x0 + 10} y="55" fontSize="11" fontWeight="600" letterSpacing="1" fill={BAND_TEXT[k]}>
              {b.label.toUpperCase()}
            </text>
          </g>
        );
      })}
      <g stroke="var(--ink)" strokeWidth="1">
        <path d={bands.slice(1).map((b) => `M${X(b.from)} 62v8`).join("")} />
      </g>
      <g fontSize="12" fontWeight="600" fill="var(--ink)" textAnchor="middle">
        {bands.slice(1).map((b) => (
          <text key={b.label} x={X(b.from)} y="84">
            {b.from}
          </text>
        ))}
      </g>
      <g fontSize="11" fill="var(--muted)" textAnchor="middle">
        <text x="20" y="84">0</text>
        <text x="1220" y="84">100</text>
      </g>
      <g data-marker>
        <path d={`M${X(v)} 66V28`} stroke="var(--signal)" strokeWidth="2" />
        <path d={`M${X(v)} 40L${X(v) - 8} 28H${X(v) + 8}Z`} fill="var(--signal)" />
        <text x={X(v)} y="16" fontSize="15" fontWeight="700" fill="var(--ink)" textAnchor="middle">
          {Math.round(v)}
        </text>
      </g>
      {error !== undefined && error > 0 && (
        <g>
          <path
            d={`M${X(v - error)} 98v8M${X(v - error)} 102H${X(v + error)}M${X(v + error)} 98v8`}
            stroke="var(--ink)"
            strokeWidth="1.5"
            fill="none"
          />
          <text x={X(v)} y="118" fontSize="11" fill="var(--muted)" textAnchor="middle">
            ±{error}
          </text>
        </g>
      )}
    </svg>
  );
}

/* ---------- TypeBar ---------- */

/** Разбивка по типам навыков: полоса на тип и общий тик порога. */
export function TypeBar({
  items,
  threshold,
  className,
}: {
  items: { label: string; value: number }[];
  threshold?: number;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-3.5", className)}>
      {items.map((it) => (
        <div key={it.label} className="flex items-center gap-3">
          <Lbl className="w-[84px] flex-none truncate">{it.label}</Lbl>
          <MeterBar value={it.value} threshold={threshold} label={it.label} className="flex-1" />
          <span className="num w-[26px] flex-none text-right">{Math.round(it.value)}</span>
        </div>
      ))}
    </div>
  );
}
