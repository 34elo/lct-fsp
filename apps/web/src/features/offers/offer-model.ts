/** Чистая логика формы приглашения: разбор вилки и проверки. Используют страница и модалка приглашения. */
import type { CircuitStep } from "@fsp/ui";

import type { OfferForCandidate, VacancyBrief } from "@/api/model";

/** «230 000» → 230000; пусто или не число → null. */
export function parseRub(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Math.round(Number(s.replace(/\s/g, "")));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Показать число с разрядами: 230000 → «230 000» (для поля ввода). */
export function groupDigits(s: string): string {
  const d = s.replace(/\D/g, "");
  return d.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

export type RangeProblem = "missing" | "inverted" | null;

export function rangeProblem(lo: number | null, hi: number | null): RangeProblem {
  if (lo === null || hi === null) return "missing";
  return hi < lo ? "inverted" : null;
}

/** «Слишком широкая вилка»: (до − от) / от > 0.5. */
export function isWideRange(lo: number | null, hi: number | null): boolean {
  return lo !== null && hi !== null && lo > 0 && hi >= lo && (hi - lo) / lo > 0.5;
}

/** Можно ли отправить: вилка корректна, есть вакансия или название. */
export function canSendOffer(opts: { lo: number | null; hi: number | null; vacancyId: string; title: string }): boolean {
  return rangeProblem(opts.lo, opts.hi) === null && (opts.vacancyId !== "" || opts.title.trim() !== "");
}

const IN_INTEREST = ["interest", "interest_opened"];
const ACCEPTED = ["accepted", "interview", "hired", "not_hired"];

export interface Funnel {
  interest: number;
  opened: number;
  invited: number;
  accepted: number;
}

interface FunnelOffer {
  status: string;
  interest_at?: string | null;
  interest_opened_at?: string | null;
  invited_at?: string | null;
}

/** Воронка работодателя: сколько приглашений дошло до каждого шага (шаги накопительные, по отметкам времени и статусу). */
export function funnelOf(offers: FunnelOffer[]): Funnel {
  const inv = (o: FunnelOffer) => !IN_INTEREST.includes(o.status) || !!o.invited_at;
  return {
    interest: offers.filter((o) => !!o.interest_at || IN_INTEREST.includes(o.status)).length,
    opened: offers.filter((o) => !!o.interest_opened_at || o.status === "interest_opened").length,
    invited: offers.filter(inv).length,
    accepted: offers.filter((o) => ACCEPTED.includes(o.status)).length,
  };
}

/** За сколько дней набрана воронка: от самого раннего приглашения до сейчас (минимум 1). */
export function funnelSpanDays(offers: { created_at: string }[], now: number): number {
  if (offers.length === 0) return 0;
  const first = Math.min(...offers.map((o) => Date.parse(o.created_at)));
  return Math.max(1, Math.ceil((now - first) / 86_400_000));
}

/** Сначала то, что ждёт ответа работодателя (интерес открыт, приняты), потом остальные; внутри — новые выше. */
export function sortOffers<T extends { status: string; created_at: string }>(offers: T[]): T[] {
  const order = (s: string) => (s === "interest_opened" || s === "accepted" || s === "interview" ? 0 : 1);
  return [...offers].sort((a, b) => order(a.status) - order(b.status) || b.created_at.localeCompare(a.created_at));
}

/** Приглашение для быстрого «Ответить»: самое свежее из принятых и идущих на интервью. */
export function lastActive<T extends { status: string; created_at: string }>(offers: T[]): T | undefined {
  return [...offers].filter((o) => o.status === "accepted" || o.status === "interview").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
}

export interface DeclineShare {
  reason: string;
  count: number;
  pct: number;
}

/** Причины отказов по убыванию; проценты от числа отказов. */
export function declineBreakdown(offers: { decline?: { reason: string } | null }[]): DeclineShare[] {
  const counts = new Map<string, number>();
  for (const o of offers) if (o.decline) counts.set(o.decline.reason, (counts.get(o.decline.reason) ?? 0) + 1);
  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  return [...counts]
    .map(([reason, count]) => ({ reason, count, pct: Math.round((count / total) * 100) }))
    .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
}


/**
 * Приглашение глазами кандидата. Сгенерированный `OfferForCandidate` ещё без `title` и `initiator`
 * и с обязательной вакансией, а API отдаёт `vacancy: null` для приглашения без вакансии (ADR-022).
 */
export type CandidateOffer = Omit<OfferForCandidate, "vacancy"> & {
  vacancy?: VacancyBrief | null;
  title?: string | null;
  description?: string | null;
  contact_method?: "platform" | "email" | "phone" | "telegram" | null;
  initiator?: "employer" | "candidate";
};

/** Название для карточки: вакансия, иначе название приглашения. */
export function offerTitle(o: Pick<CandidateOffer, "title" | "vacancy">): string {
  return o.vacancy?.title ?? o.title ?? "Приглашение";
}

/** Приглашение ждёт ответа кандидата. */
export function isAwaiting(status: string): boolean {
  return status === "sent" || status === "viewed";
}

export interface PastSummary {
  total: number;
  accepted: number;
  declined: number;
  expired: number;
}

/** Сводка «Прошлые приглашения: принято … · отклонено … · истёк …». */
export function pastSummary(past: { status: string }[]): PastSummary {
  const n = (...s: string[]) => past.filter((o) => s.includes(o.status)).length;
  return { total: past.length, accepted: n("accepted", "interview", "hired", "not_hired"), declined: n("declined"), expired: n("expired", "withdrawn") };
}

/** Шаги блока «Что дальше» после принятия. */
export function nextSteps(status: string): CircuitStep[] {
  const decided = status === "hired" || status === "not_hired";
  return [
    { id: "accepted", label: "Приглашение принят", state: "done" },
    { id: "contacts", label: "Контакты переданы", state: "done" },
    { id: "interview", label: "Интервью", state: decided ? "done" : "current" },
    { id: "decision", label: "Решение", state: decided ? "done" : "future" },
  ];
}
