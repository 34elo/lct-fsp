import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/cn";

/* Примитивы v2: карточка, заголовки, строки, чипсы, полоса.
   Сплошная обводка — подтверждено, пунктир — заявлено. Цвета только из токенов. */

/** Карточка `.card`: белая поверхность, рамка hairline, радиус 12, поле 16. `selected` — `.cat.sel`. */
export function Panel({ className, selected, ...p }: HTMLAttributes<HTMLElement> & { selected?: boolean }) {
  return (
    <section
      className={cn(
        "min-w-0 rounded-xl border border-hairline bg-card p-4",
        selected && "border-brand shadow-[0_0_0_1px_var(--brand)]",
        className,
      )}
      {...p}
    />
  );
}

/** Шапка карточки `.cap`: заголовок слева, справа метка или действие. */
export function PanelCap({ title, aside, className }: { title: ReactNode; aside?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-3 flex items-center justify-between gap-2", className)}>
      {typeof title === "string" ? <H2>{title}</H2> : title}
      {aside}
    </div>
  );
}

/** Заголовок экрана `.h1`: Mono 600, 26 px. */
export function H1({ className, ...p }: HTMLAttributes<HTMLHeadingElement>) {
  return <h1 className={cn("m-0 font-mono text-[26px] leading-[1.1] font-semibold tracking-[-0.01em]", className)} {...p} />;
}

/** Заголовок блока `.h2`: Mono 600, 16 px. */
export function H2({ className, ...p }: HTMLAttributes<HTMLHeadingElement>) {
  return <h2 className={cn("m-0 font-mono text-16 leading-[1.3] font-semibold", className)} {...p} />;
}

/** Метка `.lbl`: Mono 500, 11 px, капс, muted. */
export function Lbl({ className, ...p }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("lbl text-muted", className)} {...p} />;
}

/** Число `.num`: Mono 600. */
export function Num({ className, ...p }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("num", className)} {...p} />;
}

/** Строка списка `.rw`: разделитель сверху, у первой строки нет. */
export function ListRow({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center gap-3 border-t border-hairline py-2.5 first:border-t-0 first:pt-0", className)} {...p} />;
}

/** Контейнер чипсов `.chips`. */
export function Chips({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-wrap gap-1.5", className)} {...p} />;
}

/** Точки доверия строкой `.dts`: «●●●○». */
export function dotsText(level: number, max = 4): string {
  const v = Math.max(0, Math.min(max, Math.round(level)));
  return "●".repeat(v) + "○".repeat(max - v);
}

export type TagState = "confirmed" | "claimed" | "ghost";

/** Навык `.sk`: сплошной — подтверждён, `claimed` — пунктир, `ghost` — смежный (серый). `level` — точки доверия. */
export function SkillTag({
  name,
  level,
  state = "confirmed",
  className,
}: {
  name: ReactNode;
  level?: number;
  state?: TagState;
  className?: string;
}) {
  return (
    <span
      data-state={state}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-[5px] font-mono text-12 leading-none font-medium whitespace-nowrap",
        state === "confirmed" && "border-brand bg-tint-50 text-chip-fg",
        state === "claimed" && "border-dashed border-brand bg-card text-chip-fg dark:bg-transparent",
        state === "ghost" && "border-hairline bg-card text-muted",
        className,
      )}
    >
      {name}
      {level !== undefined && (
        <span aria-label={`доверие ${level} из 4`} className="font-mono text-[9px] leading-none font-semibold tracking-[1px] text-brand-fg">
          {dotsText(level)}
        </span>
      )}
    </span>
  );
}

/** Статус `.sb`: «подтверждён» (сплошной), заявлено (`claimed`, пунктир), `ok` — зелёный. */
export function StatusTag({
  state = "confirmed",
  className,
  ...p
}: HTMLAttributes<HTMLSpanElement> & { state?: "confirmed" | "claimed" | "ok" }) {
  return (
    <span
      data-state={state}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 font-mono text-11 leading-none font-semibold whitespace-nowrap",
        state === "confirmed" && "border-brand bg-tint-50 text-chip-fg",
        state === "claimed" && "border-dashed border-brand bg-card text-chip-fg dark:bg-transparent",
        state === "ok" && "border-success bg-success-bg text-success",
        className,
      )}
      {...p}
    />
  );
}

/** Грейд `.gb`: заливка brand — подтверждён, пунктир — заявлен. */
export function GradeTag({ claimed, className, ...p }: HTMLAttributes<HTMLSpanElement> & { claimed?: boolean }) {
  return (
    <span
      data-state={claimed ? "claimed" : "confirmed"}
      className={cn(
        "inline-flex items-center rounded-sm border border-brand px-[9px] py-[5px] font-mono text-12 leading-none font-semibold whitespace-nowrap",
        claimed ? "border-dashed bg-transparent text-brand-fg" : "bg-brand text-on-brand",
        className,
      )}
      {...p}
    />
  );
}

/** Тег `.tg`: нейтральный (профессия, фильтр). */
export function Tag({ className, ...p }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn("inline-flex items-center rounded-sm border border-tint-200 bg-tint-50 px-2 py-[5px] font-mono text-12 leading-none font-medium text-chip-fg", className)}
      {...p}
    />
  );
}

/** Полоса `.pb` (0–100). `threshold` — тик порога (`.pb.t`), `thin` — 4 px. */
export function MeterBar({
  value,
  threshold,
  thin,
  label,
  className,
}: {
  value: number;
  threshold?: number;
  thin?: boolean;
  label?: string;
  className?: string;
}) {
  const v = clamp(value);
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={v}
      aria-label={label}
      className={cn("relative rounded-sm bg-tint-100", thin ? "h-1" : "h-1.5", threshold === undefined && "overflow-hidden", className)}
    >
      <b className="block h-full rounded-sm bg-brand" style={{ width: `${v}%` }} />
      {threshold !== undefined && (
        <i data-threshold className="absolute -top-1 -bottom-1 w-0.5 rounded-sm bg-ink" style={{ left: `${clamp(threshold)}%` }} />
      )}
    </div>
  );
}

/** Строка с проверкой `.ck`: «✓ …», `warn` — «! …». */
export function CheckItem({ warn, className, children }: { warn?: boolean; className?: string; children: ReactNode }) {
  return (
    <span className={cn("flex items-start gap-2 text-13 leading-[1.4]", className)}>
      <span aria-hidden className={cn("flex-none font-bold", warn ? "text-warning" : "text-brand-fg")}>
        {warn ? "!" : "✓"}
      </span>
      <span>{children}</span>
    </span>
  );
}

/** Знак компании `.cs`: инициалы в квадрате 36 px. */
export function CompanyMark({ name, size = 36, className }: { name: string; size?: number; className?: string }) {
  const letters = name
    .split(/[\s«»"-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={cn("grid flex-none place-items-center rounded-lg border border-tint-200 bg-tint-50 font-mono text-12 font-semibold text-chip-fg", className)}
    >
      {letters || "?"}
    </span>
  );
}

export function clamp(v: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, Number.isFinite(v) ? v : lo));
}
