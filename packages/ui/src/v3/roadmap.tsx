import { Check } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";

import { cn } from "../lib/cn";

/* Roadmap (E39-11): горизонтальный роадмап роста. Этапы слева направо, на узком экране лист прокручивается пальцем. */

export type RoadmapKind = "current" | "skill" | "test" | "goal";
export type RoadmapState = "done" | "current" | "future";

export interface RoadmapAction {
  label: string;
  href: string;
  /** Внешняя ссылка: откроется в новой вкладке. */
  external?: boolean;
  /** Внутренний переход без перезагрузки; без него работает обычная ссылка. */
  onClick?: () => void;
}

export interface RoadmapStep {
  id: string;
  kind: RoadmapKind;
  state: RoadmapState;
  title: string;
  /** Подпись над заголовком: «Сейчас», «Навык», «Тест», «Цель». */
  eyebrow?: string;
  /** Пояснение под заголовком. */
  caption?: ReactNode;
  /** Выигрыш шага, например «+64% вакансий». */
  uplift?: string;
  actions?: RoadmapAction[];
}

const DOT: Record<RoadmapState, string> = {
  done: "border-brand bg-brand text-on-brand",
  current: "border-brand bg-card text-brand-fg",
  future: "border-hairline bg-card text-muted",
};

function ActionLink({ a }: { a: RoadmapAction }) {
  const click = (e: MouseEvent<HTMLAnchorElement>) => {
    if (!a.onClick || a.external || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    a.onClick();
  };
  return (
    <a
      href={a.href}
      onClick={click}
      {...(a.external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      className="inline-flex h-11 items-center text-14 font-semibold text-brand-fg underline-offset-4 hover:underline"
    >
      {a.label}
    </a>
  );
}

/** Горизонтальный роадмап: узел на линии и карточка шага под ним. */
export function Roadmap({ steps, label = "Путь роста", className }: { steps: RoadmapStep[]; label?: string; className?: string }) {
  return (
    <div
      role="region"
      aria-label={label}
      tabIndex={0}
      data-testid="roadmap"
      className={cn("-mx-4 overflow-x-auto px-4 pb-2 [scroll-snap-type:x_proximity] md:mx-0 md:px-0", className)}
    >
      <ol className="flex min-w-max gap-0">
        {steps.map((s, i) => (
          <li
            key={s.id}
            data-kind={s.kind}
            data-state={s.state}
            aria-current={s.state === "current" ? "step" : undefined}
            className="relative flex w-[248px] shrink-0 flex-col gap-3 pr-3 [scroll-snap-align:start]"
          >
            <div className="flex items-center" aria-hidden>
              <span className={cn("grid size-7 shrink-0 place-items-center rounded-full border-2 font-mono text-12 font-semibold", DOT[s.state])}>
                {s.state === "done" ? <Check className="size-4" /> : i + 1}
              </span>
              {i < steps.length - 1 && (
                <span className={cn("ml-1 h-0.5 flex-1", s.state === "done" ? "bg-brand" : "bg-hairline")} />
              )}
            </div>
            <div
              className={cn(
                "flex min-h-[148px] flex-1 flex-col gap-2 rounded-xl border bg-card p-4",
                s.state === "current" ? "border-brand shadow-[0_0_0_1px_var(--brand)]" : "border-hairline",
               
              )}
            >
              {s.eyebrow && <span className="font-mono text-12 uppercase tracking-wide text-muted">{s.eyebrow}</span>}
              <b className="text-15">{s.title}</b>
              {s.uplift && <span className="self-start rounded-full bg-tint-50 px-2 py-0.5 font-mono text-13 text-brand-fg">{s.uplift}</span>}
              {s.caption && <p className="text-13 text-muted">{s.caption}</p>}
              {s.actions && s.actions.length > 0 && (
                <div className="mt-auto flex flex-col">
                  {s.actions.map((a) => (
                    <ActionLink key={a.label + a.href} a={a} />
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
