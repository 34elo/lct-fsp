import type { RankedCandidateData } from "@fsp/ui";

import type { CandidateCard } from "@/api/model";
import { toMatchCard } from "@/features/employer/match-model";
import { FORMAT_LABEL } from "@/features/employer/text";
import { claimedVsConfirmed } from "./need-model";
import { CAT_TEXT as T } from "./text";

/* Модель страницы категории: карточка API → строка v2, неподтверждённые отдельно. */

/** Подтверждён ли грейд тестом по профессии категории. */
export const isConfirmed = (c: CandidateCard, profession: string): boolean => claimedVsConfirmed(c, profession).confirmed !== null;

/** Подтверждённые по порядку выдачи и неподтверждённые ниже (порядок внутри группы сохраняется). */
export function splitConfirmed(items: CandidateCard[], profession: string): { confirmed: CandidateCard[]; unconfirmed: CandidateCard[] } {
  const confirmed: CandidateCard[] = [];
  const unconfirmed: CandidateCard[] = [];
  for (const c of items) (isConfirmed(c, profession) ? confirmed : unconfirmed).push(c);
  return { confirmed, unconfirmed };
}

/** Уникальные названия навыков из топов загруженных карточек, по частоте, затем по алфавиту. */
export function stackOptions(items: CandidateCard[]): string[] {
  const count = new Map<string, number>();
  for (const c of items) for (const s of c.top_skills) count.set(s.name, (count.get(s.name) ?? 0) + 1);
  return [...count.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ru")).map(([n]) => n);
}

export function toRankedCard(card: CandidateCard, profession: string): RankedCandidateData {
  const base = toMatchCard(card, profession);
  const cv = claimedVsConfirmed(card, profession);
  const formats = card.formats.map((f) => FORMAT_LABEL[f] ?? f).join(" или ");
  const place = [card.city, formats ? formats.toLowerCase() : null].filter(Boolean).join(" · ");
  const reasons: RankedCandidateData["reasons"] = [];
  if (cv.status === "none") reasons.push({ text: T.reasonNone, warn: true });
  else if (cv.status === "below") reasons.push({ text: T.reasonBelow, warn: true });
  for (const e of card.match?.explanation ?? []) reasons.push({ text: e.text, warn: e.kind !== "plus" });
  const h = card.fsp_highlights[0];
  const fsp = h ? (h.place && h.of ? `${h.title}: ${h.place} из ${h.of}` : h.title) : undefined;
  return {
    pseudonym: base.pseudonym,
    match: base.match,
    grade: base.grade,
    confirmed: base.confirmed,
    note: base.confirmed ? undefined : T.gradeClaimed,
    strength: card.strength ? { value: Math.round(card.strength.value * 100), label: T.strengthLabel(Math.round(card.strength.value * 100), card.strength.rank ?? null) } : undefined,
    salary: base.salary,
    place: place ? place.charAt(0).toUpperCase() + place.slice(1) : undefined,
    skills: base.skills,
    fsp,
    reasons: reasons.slice(0, 3),
    interestedYou: card.interested_you ?? false,
  };
}
