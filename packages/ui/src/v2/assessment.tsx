import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/cn";
import { Button } from "../primitives/button";
import { MeterBar, SkillTag } from "./primitives";

/* Тест v2: шапка задания, варианты ответа, выбор строки кода, разбор ошибки. */

/** «02:41» из секунд. Отрицательные — «00:00». */
export function formatTimer(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Шапка задания: «Задание 7 / 20», полоса прогресса, таймер, «?» (пояснение). Таймер считает экран. */
export function TaskHeader({
  index,
  total,
  secondsLeft,
  onHelp,
  kindLabel,
  upTo,
  className,
}: {
  /** Номер текущего задания, с 1. */
  index: number;
  total: number;
  secondsLeft?: number;
  onHelp?: () => void;
  /** Тип задания («вывод кода»): показывается в полосе между номером и таймером. */
  kindLabel?: string;
  /** Тест адаптивный и может закончиться раньше: «из ≤20». */
  upTo?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-hairline bg-tint-50 px-3 py-2 md:gap-x-4", className)}>
      <span className="num text-[16px] md:text-[18px]" aria-label={`Задание ${index} из ${total}`}>
        Задание {index} из {upTo ? "≤" : ""}
        {total}
      </span>
      {kindLabel && (
        <span className="text-13 text-muted" data-testid="task-kind">
          · {kindLabel}
        </span>
      )}
      <MeterBar value={total ? (index / total) * 100 : 0} label="Прогресс теста" className="order-last min-w-full flex-1 sm:order-none sm:min-w-24" />
      {secondsLeft !== undefined && (
        <span className="num ml-auto text-[22px] sm:ml-0" role="timer" aria-label={`Осталось ${formatTimer(secondsLeft)}`}>
          {formatTimer(secondsLeft)}
        </span>
      )}
      {onHelp && (
        <button
          type="button"
          onClick={onHelp}
          aria-label="Пояснение"
          className="grid h-6 min-w-6 place-items-center rounded-xl bg-tint-100 px-1.5 font-semibold text-brand-fg"
        >
          ?
        </button>
      )}
    </div>
  );
}

/**
 * Вариант ответа `.opt`. `choice` — кружок выбора, `order` — ручка и номер (перетаскивание делает экран),
 * `sjt` — номер. Вся строка — кнопка.
 */
export function OptionRow({
  kind = "choice",
  selected,
  index,
  dragging,
  className,
  children,
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  kind?: "choice" | "order" | "sjt";
  selected?: boolean;
  /** Номер для order и sjt. */
  index?: number;
  /** Строка поднята при перетаскивании. */
  dragging?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role={kind === "choice" ? "radio" : undefined}
      aria-checked={kind === "choice" ? !!selected : undefined}
      aria-pressed={kind === "choice" ? undefined : !!selected}
      data-kind={kind}
      className={cn(
        "flex min-h-12 w-full items-center gap-3 rounded-[10px] border border-hairline bg-card px-3.5 py-3 text-left text-ink",
        "hover:border-brand-mid",
        selected && "border-brand bg-tint-50 shadow-[0_0_0_1px_var(--brand)]",
        dragging && "border-brand shadow-[0_8px_20px_var(--code-sel)]",
        className,
      )}
      {...p}
    >
      {kind === "choice" && (
        <span
          aria-hidden
          className={cn(
            "size-[18px] flex-none rounded-full border-2",
            selected ? "border-brand bg-[radial-gradient(var(--brand)_45%,transparent_50%)]" : "border-tint-200",
          )}
        />
      )}
      {kind === "order" && (
        <span aria-hidden className="flex-none text-16 tracking-[-2px] text-muted">
          ⋮⋮
        </span>
      )}
      {kind !== "choice" && index !== undefined && (
        <span className="grid size-[22px] flex-none place-items-center rounded-sm bg-tint-100 font-mono text-13 font-semibold text-chip-fg">{index}</span>
      )}
      <span className="num min-w-0 text-13">{children}</span>
    </button>
  );
}

/** Подсветка ключевых слов: строки кода приходят текстом, без HTML. */
const KEYWORDS = /\b(def|return|class|import|from|if|else|elif|for|while|in|not|and|or|None|True|False|async|await|const|let|function|SELECT|FROM|WHERE|JOIN|LEFT|INNER|ON)\b/g;

function highlight(line: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of line.matchAll(KEYWORDS)) {
    if (m.index > last) out.push(line.slice(last, m.index));
    out.push(
      <span key={m.index} className="text-brand-mid">
        {m[0]}
      </span>,
    );
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

/**
 * Код с номерами строк `.cd`. С `onSelect` строки выбираются кликом (задание find_bug). `marked` — жёлтая подсветка.
 * `selected` — индекс (с 0) или список индексов: со списком строки переключаются по одной (`aria-pressed`).
 * `start` — номер первой строки в подписях; `lineTestId` — data-testid строки по её номеру.
 */
export function CodeLines({
  lines,
  selected,
  onSelect,
  marked = [],
  label = "Код",
  start = 1,
  lineTestId,
  className,
}: {
  lines: string[];
  selected?: number | number[];
  onSelect?: (index: number) => void;
  marked?: number[];
  label?: string;
  start?: number;
  lineTestId?: (no: number) => string;
  className?: string;
}) {
  const box = "m-0 overflow-x-auto rounded-lg bg-code-bg px-3 py-2.5 font-mono text-12 leading-[1.65] whitespace-pre text-code-fg";
  const multi = Array.isArray(selected);
  const isOn = (i: number) => (Array.isArray(selected) ? selected.includes(i) : selected === i);
  if (!onSelect)
    return (
      <pre aria-label={label} className={cn(box, className)}>
        {lines.map((l, i) => (
          <span key={i} className={cn("-mx-3 block px-3", marked.includes(i) && "bg-code-mark")}>
            <span className="inline-block w-[22px] text-code-muted select-none">{start + i}</span>
            {highlight(l)}
          </span>
        ))}
      </pre>
    );
  return (
    <div role={multi ? "group" : "radiogroup"} aria-label={label} className={cn(box, "whitespace-normal", className)}>
      {lines.map((l, i) => (
        <button
          key={i}
          type="button"
          role={multi ? undefined : "radio"}
          aria-checked={multi ? undefined : isOn(i)}
          aria-pressed={multi ? isOn(i) : undefined}
          aria-label={`Строка ${start + i}`}
          data-testid={lineTestId?.(start + i)}
          onClick={() => onSelect(i)}
          className={cn(
            "-mx-3 block min-h-8 w-[calc(100%+1.5rem)] cursor-pointer px-3 text-left whitespace-pre text-code-fg hover:bg-code-sel/30",
            marked.includes(i) && "bg-code-mark",
            isOn(i) && "bg-code-sel shadow-[inset_3px_0_0_var(--brand-mid)]",
          )}
        >
          <span className="inline-block w-[22px] text-code-muted select-none">{start + i}</span>
          {highlight(l)}
        </button>
      ))}
    </div>
  );
}

/** Разбор ошибки `.er`: навык, суть, «Объясни ответ», фрагмент кода с подсветкой строки. */
export function ErrorBlock({
  skill,
  title,
  code,
  marked,
  onExplain,
  explainLabel = "Объясни ответ",
  action,
  children,
  className,
}: {
  skill: string;
  title: ReactNode;
  code?: string;
  /** Индексы строк кода для подсветки, с 0. */
  marked?: number[];
  onExplain?: () => void;
  explainLabel?: string;
  /** Своё действие справа вместо кнопки «Объясни ответ» (например, с загрузкой). */
  action?: ReactNode;
  /** Под кодом: разбор, ответ модели. */
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2 border-t border-hairline py-3.5 first:border-t-0 first:pt-0", className)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <SkillTag name={skill} />
        <b className="font-semibold">{title}</b>
        {action ?? (onExplain && (
          <Button variant="link" className="ml-auto h-7 px-2 no-underline sm:h-7" onClick={onExplain}>
            {explainLabel}
          </Button>
        ))}
      </div>
      {code && <CodeLines lines={code.replace(/\n$/, "").split("\n")} marked={marked} />}
      {children}
    </div>
  );
}
