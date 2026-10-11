import { BadgeCheck } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/cn";

/* Фирменные компоненты: грейд, протокол ФСП, командные сигналы. */

const ROLE_NAMES: Record<string, string> = {
  backend: "Backend",
  frontend: "Frontend",
  fullstack: "Fullstack",
  mobile: "Mobile",
  ml: "ML",
  data: "Data",
  devops: "DevOps",
  qa: "QA",
  algorithms: "Algorithms",
};

/** Псевдоним кандидата: «Backend #4821». Никаких «Candidate #». */
export function pseudonymLabel(role: string | null | undefined, number: number | string): string {
  const key = (role ?? "").trim();
  const name = ROLE_NAMES[key.toLowerCase()] ?? (key ? key.charAt(0).toUpperCase() + key.slice(1) : "Кандидат");
  return `${name} #${number}`;
}

/** Капс-метка раздела: Mono 11 px, разрядка .06em. */
export function SectionLabel({ className, ...p }: HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("font-mono text-11 font-medium uppercase tracking-[.06em] text-muted", className)} {...p} />;
}

/** Бейдж грейда: сплошной; пунктирный, если грейд предварительный. */
export function GradeBadge({
  grade,
  role,
  stack,
  preliminary = false,
  hint,
  className,
}: {
  grade: string;
  role?: string;
  stack?: string;
  preliminary?: boolean;
  /** Чего не хватает для окончательного грейда (подсказка). */
  hint?: string;
  className?: string;
}) {
  const text = [grade, role, stack].filter(Boolean).join(" · ");
  return (
    <span
      title={preliminary ? hint : undefined}
      className={cn(
        "inline-flex min-h-7 items-center gap-1.5 rounded-md border px-2.5 font-mono text-13 font-semibold",
        preliminary ? "border-dashed border-brand-mid bg-card text-brand-fg" : "border-brand bg-brand text-on-brand",
        className,
      )}
    >
      {text}
      {preliminary && <span className="text-11 font-medium uppercase tracking-[.06em]">предварительно</span>}
    </span>
  );
}

/** Плашка «Профиль подтверждён ФСП». */
export function VerifiedMark({ className, children = "Профиль подтверждён ФСП" }: { className?: string; children?: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded-full border border-tint-200 bg-tint-50 px-2.5 py-0.5 text-12 font-semibold text-brand-fg",
        className,
      )}
    >
      <BadgeCheck aria-hidden className="size-4" strokeWidth={1.5} />
      {children}
    </span>
  );
}

export interface FspResult {
  discipline: string;
  tournament: string;
  stage?: string;
  place: number;
  total?: number;
  role?: string;
  year: number;
  /** Релевантность профессии кандидата: «релевантно профессии» / «соревнование другого направления». */
  note?: string;
}

function Medal({ place }: { place: number }) {
  const medal = place >= 1 && place <= 3;
  const style =
    place === 1
      ? "border-brand bg-brand text-on-brand"
      : place === 2
        ? "border-brand-mid bg-brand-mid text-brand-deep"
        : place === 3
          ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-ink"
          : "border-transparent bg-transparent text-muted";
  return (
    <span
      role={medal ? "img" : undefined}
      aria-label={medal ? `${place} место, медаль` : undefined}
      aria-hidden={medal ? undefined : true}
      className={cn("grid size-7 shrink-0 place-items-center rounded-full border font-mono text-13 font-bold", style)}
    >
      {medal ? place : "·"}
    </span>
  );
}

/** Строка протокола ФСП: дисциплина · турнир · этап · место из N · роль · год. */
export function FspProtocol({ results, className }: { results: FspResult[]; className?: string }) {
  if (results.length === 0) {
    return <p className={cn("text-14 text-muted", className)}>Результатов ФСП пока нет</p>;
  }
  return (
    <ol className={cn("grid gap-2", className)} aria-label="Протокол ФСП">
      {results.map((r, i) => {
        const place = r.total ? `${r.place} из ${r.total}` : `${r.place} место`;
        const head = [r.discipline, r.tournament, r.stage].filter(Boolean).join(" · ");
        return (
          <li key={i} className="flex items-center gap-3">
            <Medal place={r.place} />
            <span className="text-14">
              {head} · <b className="font-mono font-semibold">{place}</b>
              {r.role ? ` · ${r.role}` : ""} · {r.year}
              {r.note && <span className="text-muted"> · {r.note}</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

const TEAM_STRENGTH = {
  strong: "сильное подтверждение",
  medium: "среднее подтверждение",
  weak: "слабое подтверждение",
} as const;

/** Командный сигнал: слова и факты, без точек. `claimed` — только из резюме, на грейд не влияет. */
export function TeamSignal({
  name,
  fact,
  strength,
  claimed = false,
}: {
  name: string;
  fact?: string;
  strength?: keyof typeof TEAM_STRENGTH;
  claimed?: boolean;
}) {
  if (claimed) {
    return (
      <p className="text-13 text-muted">
        Указано в резюме: {name} <span className="text-12">· не влияет на грейд</span>
      </p>
    );
  }
  return (
    <div className="grid gap-0.5">
      <p className="text-14">
        <b className="font-semibold">{name}</b>
        {strength && <span className="text-muted"> — {TEAM_STRENGTH[strength]}</span>}
      </p>
      {fact && <p className="text-13 text-muted">{fact}</p>}
    </div>
  );
}
