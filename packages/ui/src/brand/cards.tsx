import { ArrowRight, Bookmark, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "../lib/cn";
import { formatRub } from "../lib/format";
import { ConstellationAvatar, MatchRing, SkillChip, type TrustKind, type TrustLevel } from ".";
import { AcceptanceMeter, MatchWhy, SalaryRange, StatusBadge, type AcceptanceLevel, type OfferStatus, type WhyItem } from "./match";
import { FspProtocol, GradeBadge, SectionLabel, VerifiedMark, pseudonymLabel, type FspResult } from "./protocol";

/* Карточки: кандидат (экран A) и оффер (M2, E5). Только данные и колбэки: сеть и маршруты снаружи. */

export interface CandidateCardData {
  /** Номер псевдонима: «Backend #4821» собирается из роли и номера. */
  number: number | string;
  role: string;
  grade: string;
  stack?: string;
  gradePreliminary?: boolean;
  match: number;
  skills: { name: string; level: TrustLevel; variant?: TrustKind }[];
  fsp?: FspResult[];
  /** Ожидания: «от 230 000 ₽», формат работы и т. п. */
  expectations?: string[];
  why?: WhyItem[];
  /** Кандидат отметил именно вашу компанию («вами интересовался»). */
  interestedYou?: boolean;
}

const btn =
  "inline-flex h-10 items-center justify-center gap-1.5 rounded-lg px-4 text-14 font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

/** Анонимная карточка кандидата: слева навыки, протокол и ожидания, справа кольцо и «почему подходит». */
export function CandidateCard({
  c,
  shortlisted = false,
  onShortlist,
  onReject,
  onOpen,
  onInterest,
  className,
}: {
  c: CandidateCardData;
  shortlisted?: boolean;
  onShortlist?: () => void;
  onReject?: () => void;
  onOpen?: () => void;
  /** Первый шаг контакта: «интересен» с вилкой (E33). */
  onInterest?: () => void;
  className?: string;
}) {
  const pseudo = pseudonymLabel(c.role, c.number);
  return (
    <article aria-label={pseudo} className={cn("flex flex-col gap-4 rounded-xl border border-hairline bg-card p-[18px] shadow-xs", className)}>
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_280px]">
        <div className="grid min-w-0 content-start gap-3">
          <header className="flex items-center gap-3">
            <ConstellationAvatar seed={pseudo} />
            <div className="grid min-w-0 gap-1">
              <h3 className="font-mono text-16 font-semibold">{pseudo}</h3>
              <GradeBadge grade={c.grade} stack={c.stack} preliminary={c.gradePreliminary} className="w-fit" />
            </div>
          </header>
          {c.interestedYou && (
            <p className="inline-flex w-fit items-center gap-1.5 rounded-full border border-brand bg-tint-50 px-2.5 py-0.5 text-12 font-semibold text-brand-fg">
              <Sparkles aria-hidden className="size-3.5" />
              Вами интересовался
            </p>
          )}
          {c.fsp && c.fsp.length > 0 && <VerifiedMark className="w-fit">Подтверждено ФСП</VerifiedMark>}
          <ul className="flex flex-wrap gap-1.5" aria-label="Навыки">
            {c.skills.map((s) => (
              <li key={s.name}>
                <SkillChip name={s.name} level={s.level} variant={s.variant} />
              </li>
            ))}
          </ul>
          {c.fsp && c.fsp.length > 0 && <FspProtocol results={c.fsp.slice(0, 2)} />}
          {c.expectations && c.expectations.length > 0 && (
            <div className="text-13 text-muted">
              <SectionLabel className="mr-2 inline">Ожидания</SectionLabel>
              {c.expectations.join(" · ")}
            </div>
          )}
        </div>
        <aside className="grid min-w-0 content-start gap-3 md:border-l md:border-hairline md:pl-4">
          <div className="flex items-center gap-3">
            <MatchRing value={c.match} size={64} />
            <SectionLabel>Совпадение</SectionLabel>
          </div>
          {c.why && c.why.length > 0 && <MatchWhy items={c.why} />}
        </aside>
      </div>
      <footer className="flex flex-wrap items-center gap-2 border-t border-hairline pt-3">
        <button
          type="button"
          onClick={onShortlist}
          aria-pressed={shortlisted}
          className={cn(btn, shortlisted ? "bg-tint-100 text-brand-fg" : "bg-brand text-on-brand")}
        >
          <Bookmark aria-hidden className="size-4" fill={shortlisted ? "currentColor" : "none"} />В шорт-лист
        </button>
        {onInterest && (
          <button type="button" onClick={onInterest} className={cn(btn, "border border-brand text-brand-fg")}>
            <Sparkles aria-hidden className="size-4" />
            Интересен
          </button>
        )}
        <button type="button" onClick={onReject} className={cn(btn, "border border-hairline text-ink")}>
          Не подходит
        </button>
        <button type="button" onClick={onOpen} className={cn(btn, "ml-auto text-brand-fg")}>
          Открыть профиль
          <ArrowRight aria-hidden className="size-4" />
        </button>
      </footer>
    </article>
  );
}

export interface OfferCardData {
  company: string;
  /** Рейтинг ответственности 0–5. */
  rating?: number;
  verified?: boolean;
  from: number;
  to: number;
  title: string;
  tags?: string[];
  match?: number;
  status?: OfferStatus;
  /** «до 14 окт» — срок ответа, готовая строка. */
  deadline?: string;
  /** Нижняя граница ожиданий кандидата, если вилка ниже. */
  belowExpectation?: number;
  acceptance?: AcceptanceLevel;
}

/** Оффер кандидату (M2) и в списке работодателя (E5): вилка крупно, статус, срок, действие. */
export function OfferCard({
  o,
  actionLabel = "Открыть оффер",
  onOpen,
  extra,
  className,
}: {
  o: OfferCardData;
  actionLabel?: string;
  onOpen?: () => void;
  extra?: ReactNode;
  className?: string;
}) {
  return (
    <article aria-label={`Оффер ${o.company}`} className={cn("flex flex-col gap-3.5 rounded-xl border border-hairline bg-card p-[18px] shadow-xs", className)}>
      <header className="flex items-center gap-3">
        <div aria-hidden className="grid size-11 shrink-0 place-items-center rounded-lg bg-ink font-mono font-bold text-page">
          {o.company.slice(0, 2).toUpperCase()}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-semibold">{o.company}</h3>
          {o.rating !== undefined && (
            <p className="font-mono text-12">
              <b>{o.rating.toFixed(1)}</b> / 5 · ответственность
            </p>
          )}
        </div>
        {o.status && <StatusBadge status={o.status} />}
        {o.verified && (
          <span className="inline-flex h-6 items-center rounded-full border border-tint-200 bg-tint-50 px-2 text-11 font-semibold text-brand-fg">
            проверена
          </span>
        )}
      </header>
      {o.belowExpectation !== undefined && (
        <p role="status" className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 font-semibold text-warning-fg">
          Ниже ваших ожиданий (от {formatRub(o.belowExpectation)})
        </p>
      )}
      <SalaryRange from={o.from} to={o.to} size="offer" label="Вилка в месяц" />
      <div className="flex items-center justify-between gap-3">
        <div className="grid min-w-0 gap-2">
          <h4 className="font-semibold leading-tight">{o.title}</h4>
          {o.tags && o.tags.length > 0 && (
            <ul className="flex flex-wrap gap-1.5">
              {o.tags.map((t) => (
                <li key={t} className="rounded-md border border-tint-200 bg-tint-50 px-2.5 py-1 font-mono text-12 text-brand-deep dark:text-brand-mid">
                  {t}
                </li>
              ))}
            </ul>
          )}
        </div>
        {o.match !== undefined && <MatchRing value={o.match} />}
      </div>
      {o.acceptance && <AcceptanceMeter level={o.acceptance} />}
      {o.deadline && (
        <p className="text-13">
          Ответить до <b className="font-mono">{o.deadline}</b>
        </p>
      )}
      {extra}
      {onOpen && (
        <button type="button" onClick={onOpen} className="h-12 rounded-lg bg-brand font-semibold text-on-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">
          {actionLabel}
        </button>
      )}
    </article>
  );
}
