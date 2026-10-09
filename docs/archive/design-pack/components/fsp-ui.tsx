import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/* ---------- TrustDots ---------- */
type Trust = "verified" | "inferred" | "adjacent";
export function TrustDots({ level, kind = "verified", label }: { level: 0 | 1 | 2 | 3 | 4; kind?: Trust; label?: string }) {
  const text = label ?? `Уровень ${level} из 4, ${kind === "verified" ? "подтверждено" : kind === "inferred" ? "предположительно" : "смежный навык"}`;
  return (
    <span role="img" aria-label={text} className="inline-flex gap-[3px]">
      {[0, 1, 2, 3].map((i) => (
        <span
          key={i}
          className={cn(
            "size-[11px] rounded-full border-[1.5px]",
            i < level ? "bg-brand border-brand" : "border-brand-mid bg-transparent",
            i < level && kind === "inferred" && "border-dashed bg-transparent",
            kind === "adjacent" && "opacity-50"
          )}
        />
      ))}
    </span>
  );
}

/* ---------- SkillChip ---------- */
const chip = cva(
  "inline-flex h-[30px] items-center gap-1.5 rounded-md border px-[11px] font-mono text-[12.5px] font-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        verified: "border-tint-200 bg-tint-50 text-brand-deep",
        claimed: "border-dashed border-tint-200 bg-white text-brand-deep",
        inferred: "border-dashed border-brand-mid bg-tint-50 text-brand-deep",
        adjacent: "border-tint-100 bg-tint-50/50 text-muted",
        new: "border-tint-200 bg-white text-brand-deep",
      },
    },
    defaultVariants: { variant: "verified" },
  }
);
export function SkillChip({ name, level, variant, ...p }: { name: string; level?: 0 | 1 | 2 | 3 | 4 } & VariantProps<typeof chip> & React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span className={chip({ variant })} {...p}>
      {variant === "new" && <b className="text-[10px] text-signal">НОВЫЙ</b>}
      {name}
      {level !== undefined && <TrustDots level={level} kind={variant === "inferred" ? "inferred" : variant === "adjacent" ? "adjacent" : "verified"} />}
    </span>
  );
}

/* ---------- ConstellationAvatar ---------- */
const PATTERNS = [
  [[14, 40], [30, 16], [50, 30], [40, 52]],
  [[12, 20], [32, 12], [52, 24], [44, 50], [18, 46]],
  [[10, 32], [28, 14], [48, 18], [54, 42], [30, 54]],
  [[16, 14], [48, 12], [54, 36], [32, 52], [10, 40]],
];
export function ConstellationAvatar({ seed = 0, size = 48, dark = false }: { seed?: number; size?: number; dark?: boolean }) {
  const pts = PATTERNS[seed % PATTERNS.length];
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} role="img" aria-label="Анонимный аватар" className={cn("rounded-full border", dark ? "bg-card-dark border-brand-mid" : "bg-tint-50 border-tint-200")}>
      <polygon points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="#402FFF" strokeWidth="1.5" />
      {pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r="3" fill="#A9A1FF" />)}
    </svg>
  );
}

/* ---------- MatchRing ---------- */
export function MatchRing({ value, size = 60 }: { value: number; size?: number }) {
  return (
    <div
      role="img"
      aria-label={`Совпадение ${value} процентов`}
      style={{ width: size, height: size, background: `conic-gradient(#402FFF ${value}%, #E6E4FF 0)` }}
      className="relative grid place-items-center rounded-full"
    >
      <b className="grid place-items-center rounded-full bg-white font-mono font-bold text-brand-deep" style={{ width: size * 0.78, height: size * 0.78, fontSize: size * 0.23 }}>
        {value}%
      </b>
    </div>
  );
}

/* ---------- CandidateCard ---------- */
export interface Candidate { id: string; seed: number; role: string; match: number; fsp?: string; skills: { name: string; level: 0 | 1 | 2 | 3 | 4; variant?: "verified" | "inferred" | "adjacent" }[]; }
export function CandidateCard({ c, onOffer }: { c: Candidate; onOffer?: (id: string) => void }) {
  return (
    <article className="flex flex-col gap-3 rounded-xl border border-hairline bg-white p-[18px]">
      <header className="flex items-center gap-3">
        <ConstellationAvatar seed={c.seed} />
        <div className="min-w-0 flex-1">
          <h3 className="font-mono font-semibold">Кандидат #{c.id}</h3>
          <p className="text-[13px] text-muted">{c.role}</p>
        </div>
        <MatchRing value={c.match} />
      </header>
      {c.fsp && <p className="inline-flex w-fit items-center gap-1 rounded-full border border-tint-200 bg-tint-50 px-2.5 py-0.5 text-xs font-semibold text-brand-deep">Подтверждено ФСП · {c.fsp}</p>}
      <ul className="flex flex-wrap gap-1.5">
        {c.skills.map((s) => <li key={s.name}><SkillChip name={s.name} level={s.level} variant={s.variant} /></li>)}
      </ul>
      <button type="button" onClick={() => onOffer?.(c.id)} className="h-11 rounded-lg bg-brand font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
        Отправить оффер
      </button>
    </article>
  );
}

/* ---------- OfferCard ---------- */
export interface Offer { company: string; rating: number; verified?: boolean; from: number; to: number; title: string; tags: string[]; match: number; deadline: string; belowExpectation?: number; }
const fmt = (n: number) => n.toLocaleString("ru-RU").replace(/ /g, " ");
export function OfferCard({ o, onOpen }: { o: Offer; onOpen?: () => void }) {
  return (
    <article className="flex flex-col gap-3.5 rounded-xl border border-hairline bg-white p-[18px]">
      <header className="flex items-center gap-3">
        <div aria-hidden className="grid size-11 place-items-center rounded-[10px] bg-ink font-mono font-bold text-white">{o.company.slice(0, 2).toUpperCase()}</div>
        <div className="flex-1"><h3 className="font-semibold">{o.company}</h3><p className="font-mono text-xs"><b>{o.rating.toFixed(1)}</b> / 5 · ответственность</p></div>
        {o.verified && <span className="inline-flex h-6 items-center rounded-full border border-tint-200 bg-tint-50 px-2 text-[11px] font-semibold text-brand-deep">проверена</span>}
      </header>
      {o.belowExpectation && (
        <p role="status" className="rounded-lg border border-[#F5D28A] bg-[#FFF7E6] px-3 py-2 text-[13px] font-semibold text-[#5C3A00]">
          Ниже ваших ожиданий (от {fmt(o.belowExpectation)} ₽)
        </p>
      )}
      <div>
        <p className="font-mono text-[11px] uppercase tracking-wider text-muted">Вилка в месяц</p>
        <p className="font-mono text-[30px] font-bold leading-[1.1] tracking-tight">{fmt(o.from)} – {fmt(o.to)} ₽</p>
      </div>
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col gap-2"><h4 className="font-semibold leading-tight">{o.title}</h4><ul className="flex gap-1.5">{o.tags.map((t) => <li key={t} className="rounded-md border border-tint-200 bg-tint-50 px-2.5 py-1 font-mono text-xs text-brand-deep">{t}</li>)}</ul></div>
        <MatchRing value={o.match} />
      </div>
      <p className="text-[13px]">Ответить до <b className="font-mono">{o.deadline}</b></p>
      <button type="button" onClick={onOpen} className="h-12 rounded-lg bg-brand font-semibold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">Открыть оффер</button>
    </article>
  );
}

/* ---------- UpliftCard ---------- */
export function UpliftCard({ skill, pct, hint, onConfirm }: { skill: string; pct: number; hint: string; onConfirm?: () => void }) {
  return (
    <section className="flex flex-col gap-2.5 rounded-xl border border-hairline bg-white p-4">
      <div className="flex items-baseline justify-between"><b className="font-mono text-base">{skill}</b><b className="font-mono text-xl text-brand-deep">+{pct}%</b></div>
      <div role="img" aria-label={`Рост шансов на ${pct} процентов`} className="h-2.5 overflow-hidden rounded-full bg-tint-100"><div className="h-full bg-brand" style={{ width: `${Math.min(pct, 100)}%` }} /></div>
      <p className="text-[13px] text-muted">{hint}</p>
      <button type="button" onClick={onConfirm} className="h-11 rounded-lg border border-brand font-semibold text-brand focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">Подтвердить навык</button>
    </section>
  );
}
