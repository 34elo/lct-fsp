import { cn, ErrorState } from "@fsp/ui";
import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/mutator";
import { PAGE } from "@/shared/lib/page";
import { errorView, T } from "./text";

/** Общая колонка страниц теста. */
export function Page({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return <div className={wide ? PAGE.normal : PAGE.narrow}>{children}</div>;
}

/** Ошибка действия (кулдаун, email, согласия…) строкой с действием. */
export function ErrorLine({ error, ...rest }: { error: unknown; "data-testid"?: string }) {
  const v = errorView(error);
  return (
    <p role="alert" data-code={v.code} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-error-bg px-3 py-2 text-14 text-error" {...rest}>
      <span>{v.text}</span>
      {v.link && (
        <Link to={v.link.to} className="font-semibold underline">
          {v.link.label}
        </Link>
      )}
    </p>
  );
}

/** Ошибка загрузки страницы: 404 без «Повторить». */
export function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const v = errorView(error);
  const notFound = v.code === "not_found" || v.text === T.notFoundTitle;
  return (
    <div data-testid="assessment-error" data-code={v.code}>
      <ErrorState
        title={notFound ? T.notFoundTitle : T.errorTitle}
        description={notFound ? T.notFoundText : v.text}
        onRetry={notFound ? undefined : onRetry}
        action={
          v.link ? (
            <Link to={v.link.to} className="self-center text-14 font-semibold underline">
              {v.link.label}
            </Link>
          ) : undefined
        }
      />
    </div>
  );
}

/** Повторять только сбои сервера и сети: 4xx (404 чужой попытки, 409) повтор не лечит. */
export const retryServerOnly = (count: number, e: unknown): boolean => count < 1 && !(e instanceof ApiError && e.status < 500);

export interface ChoiceOption<V extends string> {
  value: V;
  title: ReactNode;
  text?: ReactNode;
  aside?: ReactNode;
}

/**
 * Крупные карточки выбора: радио-группа, выделение плавно «перетекает» к выбранной карточке
 * (одна подложка двигается `transform`, без анимации при `prefers-reduced-motion`). Стрелки — как у радио.
 * `lockedValue` — выбранное значение в кулдауне: подложка контуром.
 */
export function ChoiceCards<V extends string>({
  label,
  name,
  value,
  options,
  onChange,
  testid,
  lockedValue,
  className,
}: {
  label: string;
  name: string;
  value: V | "";
  options: ChoiceOption<V>[];
  onChange: (v: V) => void;
  testid: (v: V) => string;
  lockedValue?: V | "";
  className?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [rect, setRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const measure = () => {
      const sel = Array.from(el.querySelectorAll<HTMLElement>("[data-choice]")).find((n) => n.dataset.choice === value);
      setRect(sel && sel.offsetWidth > 0 ? { x: sel.offsetLeft, y: sel.offsetTop, w: sel.offsetWidth, h: sel.offsetHeight } : null);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [value, options.length]);

  const locked = !!value && lockedValue === value;
  return (
    <div ref={box} role="radiogroup" aria-label={label} className={cn("relative grid gap-3", className)}>
      {rect && (
        <span
          aria-hidden
          data-testid={`${name}-highlight`}
          className={cn(
            "pointer-events-none absolute top-0 left-0 rounded-xl border-2 transition-[transform,width,height] duration-300 ease-out motion-reduce:transition-none",
            locked ? "border-dashed border-brand bg-transparent" : "border-brand bg-tint-50",
          )}
          style={{ transform: `translate(${rect.x}px, ${rect.y}px)`, width: rect.w, height: rect.h }}
        />
      )}
      {options.map((o) => {
        const on = value === o.value;
        return (
          <label
            key={o.value}
            data-choice={o.value}
            className={cn(
              "relative flex min-h-20 cursor-pointer flex-col gap-1 rounded-xl border-2 p-4 transition-colors duration-300 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-brand",
              on && rect ? "border-transparent bg-transparent" : on ? "border-brand bg-tint-50" : "border-hairline bg-card hover:border-brand-mid",
            )}
          >
            <input type="radio" name={name} className="sr-only" checked={on} onChange={() => onChange(o.value)} data-testid={testid(o.value)} />
            <span className="flex items-start justify-between gap-2">
              <span className="text-16 font-semibold text-ink">{o.title}</span>
              {o.aside}
            </span>
            {o.text && <span className="text-13 text-muted">{o.text}</span>}
          </label>
        );
      })}
    </div>
  );
}

/** Шаги потока «направление и навыки → грейд и ожидания → тест». */
export function FlowSteps({ current, steps, label }: { current: number; steps: readonly string[]; label: string }) {
  return (
    <ol aria-label={label} className="grid grid-cols-3 gap-2" data-testid="flow-steps">
      {steps.map((s, i) => {
        const n = i + 1;
        const state = n < current ? "done" : n === current ? "current" : "future";
        return (
          <li key={s} aria-current={state === "current" ? "step" : undefined} data-testid={`flow-step-${n}`} data-state={state} className="flex flex-col gap-1.5">
            <span aria-hidden className={cn("h-1 rounded-full transition-colors duration-300 motion-reduce:transition-none", state === "future" ? "bg-hairline" : "bg-brand")} />
            <span className={cn("text-12 leading-tight font-semibold", state === "current" ? "text-ink" : "text-muted")}>
              <span className="font-mono">{n}</span> · {s}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
