/** Чистая логика формы оффера: разбор вилки и проверки. Используют страница и модалка оффера. */
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

/** Колонки канбана работодателя (макет E5): порядок как на макете. */
export const BOARD_COLUMNS = ["sent", "viewed", "interview", "accepted", "hired", "closed"] as const;
export type BoardColumn = (typeof BOARD_COLUMNS)[number];

/** Статус из API → колонка. Неизвестный статус не теряем: уходит в «Закрыто». */
export function columnOf(status: string): BoardColumn {
  return (BOARD_COLUMNS as readonly string[]).includes(status) && status !== "closed" ? (status as BoardColumn) : "closed";
}

/** Разложить офферы по колонкам, новые сверху. Пустые колонки остаются. */
export function groupByColumn<T extends { status: string; created_at: string }>(offers: T[]): Record<BoardColumn, T[]> {
  const out = Object.fromEntries(BOARD_COLUMNS.map((c) => [c, [] as T[]])) as Record<BoardColumn, T[]>;
  for (const o of [...offers].sort((a, b) => b.created_at.localeCompare(a.created_at))) out[columnOf(o.status)].push(o);
  return out;
}

export interface BoardStats {
  total: number;
  /** Доля просмотренных (всё, что ушло дальше «Отправлен»), % или null без офферов. */
  viewedPct: number | null;
  accepted: number;
  hired: number;
}

/** Сводка над доской. Принявшие: принят, интервью, нанят, не нанят (после принятия). */
export function boardStats(offers: { status: string }[]): BoardStats {
  const total = offers.length;
  const seen = offers.filter((o) => !["sent", "expired", "withdrawn"].includes(o.status)).length;
  const accepted = offers.filter((o) => ["accepted", "interview", "hired", "not_hired"].includes(o.status)).length;
  return { total, viewedPct: total ? Math.round((seen / total) * 100) : null, accepted, hired: offers.filter((o) => o.status === "hired").length };
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
 * Оффер глазами кандидата. Сгенерированный `OfferForCandidate` ещё без `title` и `initiator`
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

/** Оффер ждёт ответа кандидата. */
export function isAwaiting(status: string): boolean {
  return status === "sent" || status === "viewed";
}

export interface PastSummary {
  total: number;
  accepted: number;
  declined: number;
  expired: number;
}

/** Сводка «Прошлые офферы: принято … · отклонено … · истёк …». */
export function pastSummary(past: { status: string }[]): PastSummary {
  const n = (...s: string[]) => past.filter((o) => s.includes(o.status)).length;
  return { total: past.length, accepted: n("accepted", "interview", "hired", "not_hired"), declined: n("declined"), expired: n("expired", "withdrawn") };
}

/** Шаги блока «Что дальше» после принятия. */
export function nextSteps(status: string): CircuitStep[] {
  const decided = status === "hired" || status === "not_hired";
  return [
    { id: "accepted", label: "Оффер принят", state: "done" },
    { id: "contacts", label: "Контакты переданы", state: "done" },
    { id: "interview", label: "Интервью", state: decided ? "done" : "current" },
    { id: "decision", label: "Решение", state: decided ? "done" : "future" },
  ];
}
