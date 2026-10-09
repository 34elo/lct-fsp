import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "../lib/cn";
import { Popover, PopoverContent, PopoverTrigger } from "../primitives/overlay";

/* Фирменные компоненты (эталон — docs/archive/design-pack/components/fsp-ui.tsx), без захардкоженных цветов. */

export type TrustKind = "verified" | "inferred" | "adjacent" | "claimed" | "provisional";
export type TrustLevel = 0 | 1 | 2 | 3 | 4;

const TRUST_TEXT: Record<TrustKind, string> = {
  verified: "подтверждено",
  inferred: "предположительно",
  adjacent: "смежный навык",
  claimed: "только из резюме",
  provisional: "новый навык",
};

const STRENGTH_TEXT = ["нет подтверждения", "слабое", "среднее", "сильное", "максимум"] as const;

/** Один источник подтверждения навыка в поповере «Откуда навык». */
export interface TrustSource {
  title: string;
  detail?: string;
  strength: "strong" | "medium" | "weak" | "none";
  /** Уже отформатированная дата, например «12 сен 2026». */
  date?: string;
}

const SOURCE_STRENGTH: Record<TrustSource["strength"], string> = {
  strong: "сильно",
  medium: "средне",
  weak: "слабо",
  none: "нет силы",
};

/** 4 точки доверия. С `sources` становится кнопкой и открывает поповер «Откуда навык». */
export function TrustDots({
  level,
  kind = "verified",
  label,
  skill,
  sources,
}: {
  level: TrustLevel;
  kind?: TrustKind;
  label?: string;
  skill?: string;
  sources?: TrustSource[];
}) {
  const text = label ?? `Уровень ${level} из 4, ${TRUST_TEXT[kind]}`;
  const dots = <Dots level={level} kind={kind} text={text} />;
  if (!sources) return dots;
  return (
    <Popover>
      <PopoverTrigger
        aria-label={`Откуда навык${skill ? ` ${skill}` : ""}`}
        className="-m-1.5 inline-flex min-h-6 items-center rounded-md p-1.5 hover:bg-tint-50"
      >
        {dots}
      </PopoverTrigger>
      <PopoverContent aria-label="Откуда навык" className="w-80">
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <b className="font-mono text-14">{skill ?? "Навык"}</b>
          <span className="text-12 text-muted">{STRENGTH_TEXT[level]}</span>
        </div>
        {sources.length === 0 ? (
          <p className="text-13 text-muted">Источников пока нет.</p>
        ) : (
          <ul className="grid gap-2.5">
            {sources.map((s, i) => (
              <li key={i} className="grid gap-0.5 border-t border-hairline pt-2 first:border-0 first:pt-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="text-13 font-medium">{s.title}</span>
                  <span className="shrink-0 font-mono text-11 text-muted">{SOURCE_STRENGTH[s.strength]}</span>
                </div>
                {s.detail && <span className="text-12 text-muted">{s.detail}</span>}
                {s.date && <span className="font-mono text-11 text-muted">{s.date}</span>}
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}

function Dots({ level, kind, text }: { level: TrustLevel; kind: TrustKind; text: string }) {
  const hollow = kind === "inferred" || kind === "claimed";
  return (
    <span role="img" aria-label={text} className="inline-flex gap-[3px]">
      {[0, 1, 2, 3].map((i) => {
        const on = i < level;
        return (
          <span
            key={i}
            className={cn(
              "size-[11px] rounded-full border-[1.5px]",
              on && !hollow ? "border-brand bg-brand" : "border-brand-mid bg-transparent",
              on && hollow && "border-brand",
              on && kind === "inferred" && "border-dashed",
              kind === "adjacent" && "opacity-50",
              kind === "provisional" && "opacity-70",
            )}
          />
        );
      })}
    </span>
  );
}

const chip = cva(
  "inline-flex h-[30px] items-center gap-1.5 rounded-md border px-[11px] font-mono text-[12.5px] font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        verified: "border-tint-200 bg-tint-50 text-brand-deep dark:text-brand-mid",
        claimed: "border-dashed border-tint-200 bg-card text-brand-deep dark:text-brand-mid",
        inferred: "border-dashed border-brand-mid bg-tint-50 text-brand-deep dark:text-brand-mid",
        adjacent: "border-tint-100 bg-tint-50/50 text-muted",
        provisional: "border-tint-200 bg-card text-brand-deep dark:text-brand-mid",
      },
    },
    defaultVariants: { variant: "verified" },
  },
);

export function SkillChip({
  name,
  level,
  variant = "verified",
  isNew = false,
  sources,
  className,
  ...p
}: { name: string; level?: TrustLevel; isNew?: boolean; sources?: TrustSource[] } & VariantProps<typeof chip> & HTMLAttributes<HTMLSpanElement>) {
  const kind = (variant ?? "verified") as TrustKind;
  return (
    <span className={cn(chip({ variant }), className)} {...p}>
      {(isNew || kind === "provisional") && <b className="text-[10px] text-signal">НОВЫЙ</b>}
      {name}
      {level !== undefined && <TrustDots level={level} kind={kind} skill={name} sources={sources} />}
    </span>
  );
}

/** Детерминированный хеш строки (FNV-1a) для аватара-созвездия. */
export function hashSeed(seed: string | number): number {
  const s = String(seed);
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** 5–8 узлов, координаты выводятся из хеша псевдонима. */
export function constellationPoints(seed: string | number): [number, number][] {
  let h = hashSeed(seed);
  const next = () => {
    h = (Math.imul(h, 1664525) + 1013904223) >>> 0;
    return h / 2 ** 32;
  };
  const n = 5 + Math.floor(next() * 4);
  return Array.from({ length: n }, (_, i) => {
    const a = (i / n) * Math.PI * 2 + next() * 0.6;
    const r = 14 + next() * 14;
    return [Math.round(32 + Math.cos(a) * r), Math.round(32 + Math.sin(a) * r)] as [number, number];
  });
}

/** Аватар-созвездие: скруглённый квадрат, 5–8 узлов; `signalNode` — один красный узел («горячая точка»). */
export function ConstellationAvatar({
  seed = 0,
  size = 48,
  signalNode = false,
}: {
  seed?: string | number;
  size?: number;
  signalNode?: boolean;
}) {
  const pts = constellationPoints(seed);
  const hot = hashSeed(`${seed}:hot`) % pts.length;
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role="img"
      aria-label="Анонимный аватар"
      className="shrink-0 rounded-lg border border-tint-200 bg-tint-50"
    >
      <polygon points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--brand)" strokeWidth="1.5" />
      {pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="3" fill={signalNode && i === hot ? "var(--signal)" : "var(--brand-mid)"} />
      ))}
    </svg>
  );
}

export function MatchRing({ value, size = 60 }: { value: number; size?: number }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      role="img"
      aria-label={`Совпадение ${v} процентов`}
      style={{ width: size, height: size, background: `conic-gradient(var(--brand) ${v}%, var(--tint-100) 0)` }}
      className="relative grid place-items-center rounded-full"
    >
      <b
        className="grid place-items-center rounded-full bg-card font-mono font-bold text-brand-deep dark:text-brand-mid"
        style={{ width: size * 0.78, height: size * 0.78, fontSize: size * 0.23 }}
      >
        {v}%
      </b>
    </div>
  );
}

/** Логотип: файлы `*w.svg` — с тёмным текстом для светлой темы, без `w` — со светлым текстом для тёмной (две картинки, видна одна). */
export function Logo({ className, mark = false }: { className?: string; mark?: boolean }) {
  const base = mark ? "logo_02" : "logo_01";
  return (
    <span className={cn("inline-flex items-center", className)}>
      <img src={`/brand/${base}w.svg`} alt="ФСП Карьера" className="h-8 dark:hidden" />
      <img src={`/brand/${base}.svg`} alt="ФСП Карьера" className="hidden h-8 dark:block" />
    </span>
  );
}
