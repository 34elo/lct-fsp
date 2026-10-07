import type { CandidateCard, OfferForCompany } from "@/api/model";
import { OFFER_STATUS_LABEL } from "@/features/offers/text";
import { SHORTLIST_PAGE_TEXT as T } from "./text";

/* Модель общего шорт-листа (E38-12): статус интереса по последнему приглашению компании кандидату. */

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
