import type { Concept, Misconception, SkillCard, SkillType, TestGrade } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { T } from "./text";

export const GRADES: TestGrade[] = ["junior", "middle", "senior"];
export const SLUG_RE = /^[a-z][a-z0-9_]{1,31}$/;

let seq = 0;
export const nextId = () => ++seq;

export interface WeightRow {
  id: number;
  skill: string;
  weight: string;
}

export const weightRows = (weights: Record<string, number>): WeightRow[] =>
  Object.entries(weights).map(([skill, w]) => ({ id: nextId(), skill, weight: String(w) }));

/** Локальные ошибки формы профессии (до запроса); ключ — поле. */
export function professionErrors(
  f: { slug?: string; title: string; rows: WeightRow[] },
  creating: boolean,
): Record<string, string> {
  const e: Record<string, string> = {};
  const L = T.prof.local;
  if (creating && !SLUG_RE.test(f.slug ?? "")) e.slug = L.slug;
  const title = f.title.trim();
  if (title.length < 1 || title.length > 80) e.title = L.title;
  if (f.rows.length === 0) e.weights = L.noSkills;
  else if (f.rows.some((r) => !r.skill)) e.weights = L.skill;
  else if (new Set(f.rows.map((r) => r.skill)).size !== f.rows.length) e.weights = L.dupSkill;
  else if (f.rows.some((r) => !(Number(r.weight.replace(",", ".")) > 0 && Number(r.weight.replace(",", ".")) <= 1) || r.weight.trim() === "")) e.weights = L.weight;
  return e;
}

export const buildWeights = (rows: WeightRow[]): Record<string, number> =>
  Object.fromEntries(rows.map((r) => [r.skill, Number(r.weight.replace(",", "."))]));

export function problemText(err: unknown, dict: Record<string, string>, fallback: string): string {
  if (err instanceof ApiError && err.code && dict[err.code]) return dict[err.code]!;
  return fallback;
}

export interface CardForm {
  summary: string;
  levels: Record<TestGrade, string>;
  concepts: (Concept & { id: number })[];
  misconceptions: (Misconception & { id: number })[];
}

export const cardToForm = (c: SkillCard): CardForm => ({
  summary: c.summary,
  levels: Object.fromEntries(GRADES.map((g) => [g, (c.levels[g] ?? []).join("\n")])) as Record<TestGrade, string>,
  concepts: c.concepts.map((x) => ({ ...x, id: nextId() })),
  misconceptions: c.misconceptions.map((x) => ({ ...x, id: nextId() })),
});

export const splitLines = (s: string): string[] =>
  s.split("\n").map((x) => x.trim()).filter(Boolean);

const norm = (s: string) => s.trim().toLowerCase().replace(/\s+/g, " ");
const okLen = (s: string, min: number, max: number) => s.trim().length >= min && s.trim().length <= max;

export function cardErrors(f: CardForm): Record<string, string> {
  const e: Record<string, string> = {};
  const L = T.card.local;
  if (!okLen(f.summary, 10, 400)) e.summary = L.summary;
  const seen = new Set<string>();
  let dup = false;
  for (const g of GRADES) {
    const items = splitLines(f.levels[g]);
    if (items.length < 2 || items.length > 8 || items.some((x) => !okLen(x, 3, 300))) e[`levels-${g}`] = L.levels(T.card.grade[g]!);
    for (const x of items) {
      const k = norm(x);
      if (seen.has(k)) dup = true;
      seen.add(k);
    }
  }
  if (dup) e.levels = L.dupStatement;
  const terms = f.concepts.map((c) => norm(c.term));
  if (f.concepts.length < 3 || f.concepts.some((c) => !okLen(c.term, 1, 80) || !okLen(c.note, 3, 300)) || new Set(terms).size !== terms.length) e.concepts = L.concepts;
  if (f.misconceptions.length < 2 || f.misconceptions.some((m) => !okLen(m.claim, 3, 300) || !okLen(m.truth, 3, 300))) e.misconceptions = L.misconceptions;
  return e;
}

export function buildCard(slug: string, type: SkillType, f: CardForm): SkillCard {
  return {
    schema_version: 1,
    skill: slug,
    type,
    summary: f.summary.trim(),
    levels: Object.fromEntries(GRADES.map((g) => [g, splitLines(f.levels[g])])) as Record<TestGrade, string[]>,
    concepts: f.concepts.map((c) => ({ term: c.term.trim(), note: c.note.trim() })),
    misconceptions: f.misconceptions.map((m) => ({ claim: m.claim.trim(), truth: m.truth.trim() })),
  };
}
