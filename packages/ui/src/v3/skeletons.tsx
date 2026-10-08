import type { CSSProperties, ReactNode } from "react";

import { cn } from "../lib/cn";

/** Обёртка пресета: одна область «загрузка» для скринридера, сами полосы скрыты от него. */
function Frame({ className, children, label = "Загрузка" }: { className?: string; children: ReactNode; label?: string }) {
  return (
    <div role="status" aria-busy="true" aria-label={label} className={cn("skl-in", className)}>
      {children}
    </div>
  );
}

const Bar = ({ className, style }: { className?: string; style?: CSSProperties }) => <div aria-hidden className={cn("skl h-3.5", className)} style={style} />;

/** Строки текста: последняя короче. */
export function SkeletonLine({ lines = 1, className }: { lines?: number; className?: string }) {
  return (
    <Frame className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Bar key={i} style={{ width: lines > 1 && i === lines - 1 ? "60%" : "100%" }} />
      ))}
    </Frame>
  );
}

/** Карточка: заголовок, строки, ряд чипсов. */
export function SkeletonCard({ lines = 2, className }: { lines?: number; className?: string }) {
  return (
    <Frame className={cn("flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4", className)}>
      <Bar className="h-4 w-2/5" />
      {Array.from({ length: lines }, (_, i) => (
        <Bar key={i} style={{ width: i === lines - 1 ? "70%" : "100%" }} />
      ))}
      <div className="flex gap-2">
        <Bar className="h-6 w-16" />
        <Bar className="h-6 w-20" />
        <Bar className="h-6 w-12" />
      </div>
    </Frame>
  );
}

/** Таблица: шапка и строки. */
export function SkeletonTable({ rows = 5, cols = 4, className }: { rows?: number; cols?: number; className?: string }) {
  return (
    <Frame className={cn("flex flex-col overflow-hidden rounded-xl border border-hairline bg-card", className)}>
      {Array.from({ length: rows + 1 }, (_, r) => (
        <div key={r} className={cn("grid gap-4 border-b border-hairline px-4 py-3 last:border-b-0", r === 0 && "bg-tint-50")} style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
          {Array.from({ length: cols }, (_, c) => (
            <Bar key={c} className={r === 0 ? "h-2.5" : undefined} style={{ width: `${c === 0 ? 85 : 55 + ((r * 7 + c * 13) % 40)}%` }} />
          ))}
        </div>
      ))}
    </Frame>
  );
}

const CHART = [42, 68, 55, 80, 36, 62, 74, 50];

/** График: столбцы разной высоты и ось. */
export function SkeletonChart({ height = 160, className }: { height?: number; className?: string }) {
  return (
    <Frame className={cn("flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4", className)}>
      <Bar className="h-4 w-1/3" />
      <div className="flex items-end gap-2 border-b border-hairline" style={{ height }}>
        {CHART.map((h, i) => (
          <Bar key={i} className="flex-1 rounded-b-none" style={{ height: `${h}%` }} />
        ))}
      </div>
    </Frame>
  );
}

/** Профиль: аватар, имя, метрики, чипсы. */
export function SkeletonProfile({ className }: { className?: string }) {
  return (
    <Frame className={cn("flex flex-col gap-4 rounded-xl border border-hairline bg-card p-4", className)}>
      <div className="flex items-center gap-3">
        <Bar className="size-12 shrink-0 rounded-full" />
        <div className="flex flex-1 flex-col gap-2">
          <Bar className="h-4 w-1/2" />
          <Bar className="w-1/3" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => (
          <Bar key={i} className="h-14" />
        ))}
      </div>
      <div className="flex flex-wrap gap-2">
        {[16, 20, 14, 18].map((w, i) => (
          <Bar key={i} className="h-6" style={{ width: w * 4 }} />
        ))}
      </div>
    </Frame>
  );
}
