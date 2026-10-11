import { AlertTriangle, Ban, Check, CircleDashed, Clock, Eye, Handshake, MailOpen, MessageSquare, Sparkles, UserX, X, type LucideIcon } from "lucide-react";

import { cn } from "../lib/cn";
import { formatRubRange } from "../lib/format";
import { SectionLabel } from "./protocol";

/* Фирменные: обоснование совпадения, вилка, статусы оффера, вероятность принятия, рост, лог, схема этапов. */

export type WhyKind = "ok" | "warn" | "no";
export interface WhyItem {
  kind: WhyKind;
  text: string;
}

const WHY: Record<WhyKind, { icon: LucideIcon; label: string; cls: string }> = {
  ok: { icon: Check, label: "Подходит", cls: "text-success" },
  warn: { icon: AlertTriangle, label: "Есть нюанс", cls: "text-warning-fg" },
  no: { icon: X, label: "Не подходит", cls: "text-error" },
};

/** «Почему подходит»: пункты ✓ / ⚠ / ✕. Смысл несут иконка и скрытая подпись, а не только цвет. */
export function MatchWhy({ items, className }: { items: WhyItem[]; className?: string }) {
  return (
    <ul className={cn("grid gap-1.5", className)} aria-label="Почему подходит">
      {items.map((it, i) => {
        const w = WHY[it.kind];
        const Icon = w.icon;
        return (
          <li key={i} className="flex items-start gap-2 text-13">
            <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", w.cls)} strokeWidth={2} />
            <span className="sr-only">{w.label}: </span>
            <span>{it.text}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Вилка в месяц. `size="offer"` — 30 px, как в оффере. */
export function SalaryRange({
  from,
  to,
  size = "md",
  label,
  className,
}: {
  from: number;
  to: number;
  size?: "md" | "offer";
  /** Подпись над суммой, например «Вилка в месяц». */
  label?: string;
  className?: string;
}) {
  return (
    <div className={className}>
      {label && <SectionLabel>{label}</SectionLabel>}
      <p className={cn("font-mono font-bold leading-[1.1] tracking-tight", size === "offer" ? "text-[30px]" : "text-16")}>
        {formatRubRange(from, to)}
      </p>
    </div>
  );
}

/** Статусы оффера — те же значения, что `OfferStatus` в контракте. */
export type OfferStatus = "sent" | "viewed" | "accepted" | "declined" | "expired" | "withdrawn" | "interview" | "hired" | "not_hired" | "interest" | "interest_opened";

const STATUS: Record<OfferStatus, { icon: LucideIcon; label: string; cls: string }> = {
  sent: { icon: Clock, label: "Отправлен", cls: "border-brand-mid bg-card text-brand-deep dark:text-brand-mid" },
  viewed: { icon: Eye, label: "Просмотрен", cls: "border-brand-mid bg-tint-50 text-brand-deep dark:text-brand-mid" },
  accepted: { icon: Check, label: "Принят", cls: "border-success bg-success-bg text-success" },
  declined: { icon: X, label: "Отклонён", cls: "border-error bg-error-bg text-error" },
  expired: { icon: CircleDashed, label: "Истёк", cls: "border-hairline bg-card text-muted" },
  withdrawn: { icon: Ban, label: "Отозван", cls: "border-hairline bg-card text-muted" },
  interview: { icon: MessageSquare, label: "Собеседование", cls: "border-brand bg-tint-50 text-brand-fg" },
  hired: { icon: Handshake, label: "Нанят", cls: "border-success bg-success-bg text-success" },
  not_hired: { icon: UserX, label: "Не нанят", cls: "border-hairline bg-card text-muted" },
  interest: { icon: Sparkles, label: "Интерес", cls: "border-brand-mid bg-tint-50 text-brand-deep dark:text-brand-mid" },
  interest_opened: { icon: MailOpen, label: "Интерес открыт", cls: "border-brand bg-tint-50 text-brand-fg" },
};

export const OFFER_STATUS_LABEL = Object.fromEntries(Object.entries(STATUS).map(([k, v]) => [k, v.label])) as Record<OfferStatus, string>;

/** Статус оффера: иконка + слово. */
export function StatusBadge({ status, className }: { status: OfferStatus; className?: string }) {
  const s = STATUS[status];
  const Icon = s.icon;
  return (
    <span className={cn("inline-flex h-6 items-center gap-1 rounded-full border px-2.5 text-12 font-semibold", s.cls, className)}>
      <Icon aria-hidden className="size-3.5" strokeWidth={2} />
      {s.label}
    </span>
  );
}

export type AcceptanceLevel = "low" | "medium" | "high";
const ACCEPT = { low: ["низкая", 1], medium: ["средняя", 2], high: ["высокая", 3] } as const;

/** Вероятность принятия оффера: три деления и слово. */
export function AcceptanceMeter({ level, className }: { level: AcceptanceLevel; className?: string }) {
  const [word, n] = ACCEPT[level];
  return (
    <div className={cn("flex items-center gap-2 text-13", className)}>
      <span role="img" aria-label={`Вероятность принятия: ${word}`} className="inline-flex gap-[3px]">
        {[1, 2, 3].map((i) => (
          <span key={i} className={cn("h-2 w-5 rounded-full", i <= n ? "bg-brand" : "bg-tint-100")} />
        ))}
      </span>
      <span aria-hidden>
        Вероятность принятия: <b className="font-semibold">{word}</b>
      </span>
    </div>
  );
}

/** Карточка роста: навык, прирост шансов, подсказка и действие. */
export function UpliftCard({
  skill,
  pct,
  hint,
  actionLabel = "Подтвердить навык",
  onConfirm,
  className,
}: {
  skill: string;
  pct: number;
  hint: string;
  actionLabel?: string;
  onConfirm?: () => void;
  className?: string;
}) {
  return (
    <section className={cn("flex flex-col gap-2.5 rounded-xl border border-hairline bg-card p-4", className)}>
      <div className="flex items-baseline justify-between">
        <b className="font-mono text-16">{skill}</b>
        <b className="font-mono text-20 text-brand-deep dark:text-brand-mid">+{pct}%</b>
      </div>
      <div role="img" aria-label={`Рост шансов на ${pct} процентов`} className="h-2.5 overflow-hidden rounded-full bg-tint-100">
        <div className="h-full bg-brand" style={{ width: `${Math.max(0, Math.min(pct, 100))}%` }} />
      </div>
      <p className="text-13 text-muted">{hint}</p>
      {onConfirm && (
        <button
          type="button"
          onClick={onConfirm}
          className="h-11 rounded-lg border border-brand font-semibold text-brand-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {actionLabel}
        </button>
      )}
    </section>
  );
}

export interface CircuitStep {
  id: string;
  label: string;
  state: "done" | "current" | "future";
}

/** Схема этапов: узлы на линии. Текущий узел красный, будущие пунктиром. */
export function CircuitLine({
  steps,
  orientation = "vertical",
  className,
}: {
  steps: CircuitStep[];
  orientation?: "vertical" | "horizontal";
  className?: string;
}) {
  const v = orientation === "vertical";
  return (
    <ol className={cn("flex", v ? "flex-col" : "flex-row items-start", className)} aria-label="Этапы">
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        const future = s.state === "future";
        const nextFuture = !last && steps[i + 1].state === "future";
        return (
          <li
            key={s.id}
            aria-current={s.state === "current" ? "step" : undefined}
            className={cn("flex", v ? "gap-3" : "min-w-0 flex-1 flex-col gap-2")}
          >
            <span className={cn("flex items-center", v ? "flex-col" : "flex-row")}>
              <span
                aria-hidden
                className={cn(
                  "size-3.5 shrink-0 rounded-full border-2",
                  s.state === "done" && "border-brand bg-brand",
                  s.state === "current" && "border-signal bg-signal",
                  future && "border-dashed border-brand-mid bg-card",
                )}
              />
              {!last && (
                <span
                  aria-hidden
                  className={cn(
                    v ? "my-1 min-h-6 w-0 flex-1 border-l-2" : "mx-1 h-0 min-w-6 flex-1 border-t-2",
                    future || nextFuture ? "border-dashed border-brand-mid" : "border-solid border-brand",
                  )}
                />
              )}
            </span>
            <span className={cn("text-13", v && "pb-3", s.state === "current" && "font-semibold", future && "text-muted")}>
              {s.label}
              <span className="sr-only">{s.state === "done" ? " — пройден" : s.state === "current" ? " — текущий" : " — впереди"}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export interface LogLine {
  id: string;
  text: string;
  state: "done" | "active" | "fail";
}

const MARK: Record<LogLine["state"], string> = { done: "✓", active: "◌", fail: "✕" };

/** Терминальный лог этапов долгой задачи. Строки приходят снаружи, компонент только рисует. */
export function BuildLog({ title, lines, className }: { title: string; lines: LogLine[]; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-hairline bg-tint-50 p-3 font-mono text-13 leading-6", className)}>
      <p className="text-muted">$ {title}</p>
      <ul role="log" aria-live="polite" aria-label={title} className="flex flex-col">
        {lines.map((l) => (
          <li
            key={l.id}
            className={cn(
              "fsp-log-line flex gap-2",
              l.state === "done" && "text-brand-deep dark:text-brand-mid",
              l.state === "active" && "text-ink",
              l.state === "fail" && "text-error",
            )}
          >
            <span aria-hidden className={cn(l.state === "active" && "fsp-spin")}>
              {MARK[l.state]}
            </span>
            <span>{l.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
