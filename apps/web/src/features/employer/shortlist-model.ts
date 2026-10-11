import type { CandidateCard, OfferForCompany } from "@/api/model";
import { OFFER_STATUS_LABEL } from "@/features/offers/text";
import { formatRub } from "@fsp/ui";
import { fspResults } from "./candidate-model";
import { toMatchCard } from "./match-model";
import { FORMAT_LABEL, SHORTLIST_PAGE_TEXT as T } from "./text";

/* Модель общего шорт-листа: статус интереса по последнему приглашению компании кандидату. */

export type InterestState = "none" | "waiting" | "opened" | "other";

/** Последнее приглашение или интерес компании каждому кандидату (по `created_at`). */
export function latestOfferByCandidate(offers: OfferForCompany[]): Map<string, OfferForCompany> {
  const out = new Map<string, OfferForCompany>();
  for (const o of offers) {
    const id = o.candidate?.pseudo_id;
    if (!id) continue;
    const prev = out.get(id);
    if (!prev || prev.created_at < o.created_at) out.set(id, o);
  }
  return out;
}

export function interestState(o: OfferForCompany | undefined): InterestState {
  if (!o) return "none";
  if (o.status === "interest") return "waiting";
  if (o.status === "interest_opened") return "opened";
  return "other";
}

/** Подпись статуса: макет — «интерес не отправлен» / «ожидает ответа». */
export function interestLabel(o: OfferForCompany | undefined): string {
  const s = interestState(o);
  if (s === "none") return T.noInterest;
  if (s === "waiting") return T.waiting;
  if (s === "opened") return T.opened;
  return (OFFER_STATUS_LABEL[o?.status ?? ""] ?? o?.status ?? "").toLowerCase();
}

/** Кого приглашать главной кнопкой: сначала открывшие интерес, затем без контакта вовсе. */
export function nextToInvite(cards: CandidateCard[], offers: Map<string, OfferForCompany>): { card: CandidateCard; interest?: OfferForCompany } | null {
  for (const c of cards) {
    const o = offers.get(c.pseudo_id);
    if (interestState(o) === "opened") return { card: c, interest: o };
  }
  const fresh = cards.find((c) => !offers.has(c.pseudo_id));
  return fresh ? { card: fresh } : null;
}

export const COMPARE_MIN = 2;
export const COMPARE_MAX = 4;

/** Отметка для сравнения: добавить/снять, не больше `COMPARE_MAX`. Порядок — как отмечали. */
export function togglePick(picked: string[], id: string): string[] {
  if (picked.includes(id)) return picked.filter((x) => x !== id);
  return picked.length >= COMPARE_MAX ? picked : [...picked, id];
}

export interface CompareRow {
  key: keyof typeof T.rows;
  cells: string[];
}

/** Строки сравнения 2–4 кандидатов: одна строка — один признак, ячейки — по кандидатам. */
export function compareRows(cards: CandidateCard[], offers: Map<string, OfferForCompany>): CompareRow[] {
  const d = cards.map((c) => ({ c, m: toMatchCard(c, c.categories?.[0]?.profession ?? c.primary_role ?? "") }));
  const fsp = (c: CandidateCard) => {
    const list = fspResults(c.fsp_highlights);
    const top = list[0];
    if (!top) return T.noFsp;
    const first = top.place ? T.fspBest(top.discipline, top.place, top.year) : `${top.discipline}, ${top.year}`;
    return list.length > 1 ? `${first} · ${T.fspMore(list.length - 1)}` : first;
  };
  return [
    { key: "grade", cells: d.map(({ m }) => m.grade) },
    { key: "proof", cells: d.map(({ m }) => (m.confirmed ? T.confirmed : T.claimed)) },
    { key: "skills", cells: d.map(({ c }) => c.top_skills.slice(0, 5).map((s) => s.name).join(", ") || "—") },
    { key: "salary", cells: d.map(({ c }) => (c.salary_min ? formatRub(c.salary_min) : "—")) },
    { key: "format", cells: d.map(({ c }) => c.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ") || "—") },
    { key: "city", cells: d.map(({ c }) => c.city ?? "—") },
    { key: "fsp", cells: d.map(({ c }) => fsp(c)) },
    { key: "interest", cells: d.map(({ c }) => interestLabel(offers.get(c.pseudo_id))) },
  ];
}
