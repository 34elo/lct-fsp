import { useId, type FormEvent } from "react";

import { Button, cn, Search as SearchIcon, X } from "@fsp/ui";

import type { FilterChip } from "@/api/model";
import { chipApprox, chipText } from "./search-model";
import { SEARCH_TEXT as T } from "./text";

/**
 * Строка запроса (A) и «текст → чипсы». Текст разбирает `POST /search/parse`, чипсы появляются
 * по одному слева направо (`fsp-chip-in`, шаг 80 мс); при prefers-reduced-motion — сразу, без перехода.
 * Распознанное объявляется скринридеру одной строкой.
 */
export function QueryBar({
  value,
  onChange,
  onSubmit,
  pending,
  chips,
  parseKey,
  error,
  onRemoveChip,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  pending: boolean;
  /** Чипсы, которые ещё отражают фильтры; `null` — запрос не разбирали. */
  chips: FilterChip[] | null;
  /** Меняется на каждый разбор: заново проигрываем появление чипсов. */
  parseKey: number;
  error: string | null;
  onRemoveChip: (c: FilterChip) => void;
}) {
  const id = useId();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onSubmit();
  };
  const summary = chips && chips.length > 0 ? `${T.recognized}: ${chips.map(chipText).join(", ")}` : "";
  return (
    <section aria-label={T.queryLabel} className="grid gap-3">
      <form role="search" onSubmit={submit} className="flex gap-2 sm:gap-3">
        <label htmlFor={id} className="sr-only">
          {T.queryLabel}
        </label>
        <span className="relative min-w-0 flex-1">
          <SearchIcon aria-hidden className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-brand-fg" />
          <input
            id={id}
            type="search"
            value={value}
            maxLength={500}
            onChange={(e) => onChange(e.target.value)}
            placeholder={T.queryPlaceholder}
            aria-busy={pending || undefined}
            className="h-14 w-full rounded-lg border border-brand-mid bg-card pl-12 pr-4 text-16 text-ink placeholder:text-muted focus:border-brand focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          />
        </span>
        <Button type="submit" size="lg" loading={pending} className="h-14 shrink-0 px-5 sm:px-8">
          {T.find}
        </Button>
      </form>

      <p role="status" aria-live="polite" className="sr-only">
        {pending ? T.parsing : summary}
      </p>

      {error && (
        <p role="alert" className="text-13 text-error">
          {error}
        </p>
      )}

      {chips && chips.length === 0 && !pending && !error && <p className="text-13 text-muted">{T.nothingRecognized}</p>}

      {chips && chips.length > 0 && (
        <div key={parseKey} className="flex flex-wrap items-center gap-2" aria-hidden={pending || undefined}>
          <span className="lbl mr-1 text-muted">{T.recognized}</span>
          <ul className="flex min-w-0 flex-wrap gap-2" aria-label={T.recognized}>
            {chips.map((c, i) => {
              const approx = chipApprox(c);
              const text = chipText(c);
              return (
                <li
                  key={`${c.key}:${JSON.stringify(c.value)}`}
                  className={cn(
                    "fsp-chip-in inline-flex h-[30px] max-w-full items-center gap-1.5 rounded-md border pl-[11px] pr-1 font-mono text-[12.5px] font-medium text-brand-deep dark:text-brand-mid",
                    approx ? "border-dashed border-brand-mid bg-card" : "border-tint-200 bg-tint-50",
                  )}
                  style={{ animationDelay: `${i * 80}ms` }}
                >
                  <span className="truncate">
                    {text}
                    {approx && <span aria-label=", приблизительно"> ~</span>}
                  </span>
                  <button
                    type="button"
                    onClick={() => onRemoveChip(c)}
                    aria-label={`Убрать условие «${text}»`}
                    className="grid size-6 shrink-0 place-items-center rounded-sm text-muted hover:bg-tint-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
                  >
                    <X aria-hidden className="size-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
          {chips.some(chipApprox) && <span className="text-12 text-muted">{T.approxHint}</span>}
        </div>
      )}
    </section>
  );
}
