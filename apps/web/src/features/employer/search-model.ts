import type { CandidateCardData, FspResult, TrustLevel, WhyItem } from "@fsp/ui";
import { formatRub } from "@fsp/ui";

import type { CandidateCard, FilterChip, SearchFilters, SearchRequestSort } from "@/api/model";
import { dots, GRADE_LABEL } from "@/features/profile/text";
import { FORMAT_LABEL, FSP_LEVEL_LABEL, percent } from "./text";

/* Модель экрана A: форма фильтров, разбор запроса и перевод карточки API в CandidateCard из @fsp/ui. */

/** Грейды по порядку: диапазон `grade_min..grade_max` ↔ отмеченные галочки. */
export const GRADES = Object.keys(GRADE_LABEL);

export interface SearchForm {
  roles: string[];
  grades: string[];
  formats: string[];
  skills: string[];
  skillsNice: string[];
  employment: string[];
  cities: string[];
  salaryMax: number | null;
  minTrust: number | null;
  fspOnly: boolean;
  activeOnly: boolean;
  relocationOk: boolean;
  semantic: string;
  sort: SearchRequestSort;
}

export const EMPTY_FORM: SearchForm = {
  roles: [],
  grades: [],
  formats: [],
  skills: [],
  skillsNice: [],
  employment: [],
  cities: [],
  salaryMax: null,
  minTrust: null,
  fspOnly: false,
  activeOnly: false,
  relocationOk: false,
  semantic: "",
  sort: "match",
};

/** Все грейды от `min` до `max` включительно (пустой край — открытый). */
export function gradeRange(min?: string | null, max?: string | null): string[] {
  if (!min && !max) return [];
  const lo = min ? GRADES.indexOf(min) : 0;
  const hi = max ? GRADES.indexOf(max) : GRADES.length - 1;
  if (lo < 0 || hi < 0 || lo > hi) return [];
  return GRADES.slice(lo, hi + 1);
}

const ordered = (grades: string[]) => GRADES.filter((g) => grades.includes(g));

export function toFilters(f: SearchForm): SearchFilters {
  const out: SearchFilters = {};
  if (f.roles.length) out.roles = f.roles as never;
  const g = ordered(f.grades);
  if (g.length) {
    out.grade_min = g[0] as never;
    out.grade_max = g[g.length - 1] as never;
  }
  if (f.formats.length) out.formats = f.formats as never;
  if (f.skills.length) out.skills_must = f.skills.map((slug) => ({ slug }));
  if (f.skillsNice.length) out.skills_nice = f.skillsNice;
  if (f.employment.length) out.employment_types = f.employment as never;
  if (f.cities.length) out.cities = f.cities;
  if (f.salaryMax !== null) out.salary_max = f.salaryMax;
  if (f.minTrust !== null) out.min_trust = f.minTrust as never;
  if (f.fspOnly) out.fsp_only = true;
  if (f.activeOnly) out.active_only = true;
  if (f.relocationOk) out.relocation_ok = true;
  if (f.semantic.trim()) out.semantic_text = f.semantic.trim();
  return out;
}

/** Фильтры из `POST /search/parse` заменяют форму; сортировка остаётся прежней. */
export function fromParsed(filters: SearchFilters, sort: SearchRequestSort): SearchForm {
  return {
    roles: [...(filters.roles ?? [])],
    grades: gradeRange(filters.grade_min, filters.grade_max),
    formats: [...(filters.formats ?? [])],
    skills: (filters.skills_must ?? []).map((s) => s.slug),
    skillsNice: [...(filters.skills_nice ?? [])],
    employment: [...(filters.employment_types ?? [])],
    cities: [...(filters.cities ?? [])],
    salaryMax: filters.salary_max ?? null,
    minTrust: filters.min_trust ?? null,
    fspOnly: !!filters.fsp_only,
    activeOnly: !!filters.active_only,
    relocationOk: !!filters.relocation_ok,
    semantic: filters.semantic_text ?? "",
    sort,
  };
}

const slugOf = (v: unknown): string => (typeof v === "object" && v !== null ? String((v as { slug?: unknown }).slug ?? "") : String(v));

/** Чипс ещё отражает форму? Если пользователь поменял фильтр слева, чипс пропадает. */
export function chipActive(c: FilterChip, f: SearchForm): boolean {
  switch (c.key) {
    case "roles":
      return f.roles.includes(String(c.value));
    case "grade_min":
    case "grade_max":
      return f.grades.includes(String(c.value));
    case "skills_must":
      return f.skills.includes(slugOf(c.value));
    case "skills_nice":
      return f.skillsNice.includes(String(c.value));
    case "formats":
      return f.formats.includes(String(c.value));
    case "employment_types":
      return f.employment.includes(String(c.value));
    case "cities":
      return f.cities.includes(String(c.value));
    case "salary_max":
      return f.salaryMax === Number(c.value);
    case "min_trust":
      return f.minTrust === Number(c.value);
    case "fsp_only":
      return f.fspOnly;
    case "active_only":
      return f.activeOnly;
    case "relocation_ok":
      return f.relocationOk;
    case "semantic_text":
      return f.semantic.trim() !== "";
    default:
      return false;
  }
}

/** Крестик на чипсе: убираем ровно это условие. Снятый край грейда оставляет второй край. */
export function removeChip(c: FilterChip, f: SearchForm): SearchForm {
  const v = String(c.value);
  const drop = (xs: string[], x: string) => xs.filter((y) => y !== x);
  switch (c.key) {
    case "roles":
      return { ...f, roles: drop(f.roles, v) };
    case "grade_min":
    case "grade_max": {
      const rest = ordered(drop(f.grades, v));
      return { ...f, grades: rest };
    }
    case "skills_must":
      return { ...f, skills: drop(f.skills, slugOf(c.value)) };
    case "skills_nice":
      return { ...f, skillsNice: drop(f.skillsNice, v) };
    case "formats":
      return { ...f, formats: drop(f.formats, v) };
    case "employment_types":
      return { ...f, employment: drop(f.employment, v) };
    case "cities":
      return { ...f, cities: drop(f.cities, v) };
    case "salary_max":
      return { ...f, salaryMax: null };
    case "min_trust":
      return { ...f, minTrust: null };
    case "fsp_only":
      return { ...f, fspOnly: false };
    case "active_only":
      return { ...f, activeOnly: false };
    case "relocation_ok":
      return { ...f, relocationOk: false };
    case "semantic_text":
      return { ...f, semantic: "" };
    default:
      return f;
  }
}

/** Чипс понят приблизительно (смысловой остаток, LLM или низкая уверенность) — рисуем пунктиром с «~». */
export function chipApprox(c: FilterChip): boolean {
  return c.key === "semantic_text" || c.source === "llm" || c.confidence < 0.7;
}

/** Короткая подпись чипса: «Навык: Python» → «Python». */
export function chipText(c: FilterChip): string {
  const i = c.label.indexOf(": ");
  return i >= 0 ? c.label.slice(i + 2) : c.label;
}

const WHY_KIND: Record<string, WhyItem["kind"]> = { plus: "ok", warn: "warn", minus: "no" };

/** «Backend #4821» → роль и номер; иначе псевдоним целиком без номера. */
function splitPseudonym(card: CandidateCard): { role: string; number: string } {
  const m = /^(.*\S)\s+#(\S+)$/.exec(card.pseudonym);
  if (m) return { role: m[1]!, number: m[2]! };
  return { role: card.primary_role ?? "Кандидат", number: card.pseudo_id.slice(0, 4) };
}

function fspResults(card: CandidateCard): FspResult[] {
  return card.fsp_highlights
    .filter((h) => typeof h.place === "number")
    .map((h) => ({
      discipline: h.title,
      tournament: "",
      stage: FSP_LEVEL_LABEL[h.level] ?? h.level,
      place: h.place!,
      total: h.of ?? undefined,
      year: h.year,
      note: h.note ?? undefined,
    }));
}

/** Основной стек приходит слагом: подписываем названием из топ-навыков, если оно есть. */
function stackName(card: CandidateCard): string | undefined {
  const slug = card.primary_stack[0];
  if (!slug) return undefined;
  return card.top_skills.find((s) => s.slug === slug)?.name ?? slug;
}

/** Карточка API → данные CandidateCard из @fsp/ui. Только анонимные поля DTO. */
export function toCardData(card: CandidateCard): CandidateCardData {
  const { role, number } = splitPseudonym(card);
  const formats = card.formats.map((f) => FORMAT_LABEL[f] ?? f).join(" или ");
  const expectations = [
    card.salary_min ? `от ${formatRub(card.salary_min)}` : null,
    formats ? formats.charAt(0).toUpperCase() + formats.slice(1).toLowerCase() : null,
    card.city,
  ].filter((x): x is string => !!x);
  return {
    number,
    role,
    grade: card.grade ? (GRADE_LABEL[card.grade] ?? card.grade) : "Грейд не определён",
    stack: stackName(card),
    gradePreliminary: card.grade_preliminary,
    match: card.match ? percent(card.match.score) : 0,
    skills: card.top_skills.slice(0, 6).map((s) => ({
      name: s.name,
      level: dots(s.level) as TrustLevel,
      variant: s.sources.length > 0 && s.sources.every((x) => x === "resume" || x === "self") ? "claimed" : "verified",
    })),
    fsp: fspResults(card),
    expectations,
    interestedYou: card.interested_you ?? false,
    why: (card.match?.explanation ?? []).slice(0, 4).map((e) => ({ kind: WHY_KIND[e.kind] ?? "warn", text: e.text })),
  };
}
