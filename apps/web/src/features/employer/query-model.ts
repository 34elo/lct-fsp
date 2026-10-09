import type { Grade, SearchFilters, TrustLevel, WorkFormat } from "@/api/model";

/*
 * Поиск сотрудников (E39-21): условия запроса живут в URL. Навыки и профессия — чипсы строки запроса
 * (подсказки системы `/taxonomy/*\/suggest`, свободный текст — `/search/parse`), остальное — панель фильтров.
 * Условия превращаются в `SearchFilters` потребности (`POST /needs`), её категории — в выдачу.
 */

/** Грейды теста: категория — «профессия × один из трёх грейдов». */
export const TEST_GRADES = ["junior", "middle", "senior"] as const;
export type TestGrade = (typeof TEST_GRADES)[number];

export const FORMATS = ["remote", "hybrid", "office"] as const;

export interface Criteria {
  skills: string[];
  profession: string | null;
  grades: TestGrade[];
  trust: number | null;
  fsp: boolean;
  confirmed: boolean;
  cities: string[];
  salaryFrom: number | null;
  salaryTo: number | null;
  relocation: boolean;
  formats: string[];
}

export const EMPTY_CRITERIA: Criteria = {
  skills: [],
  profession: null,
  grades: [],
  trust: null,
  fsp: false,
  confirmed: false,
  cities: [],
  salaryFrom: null,
  salaryTo: null,
  relocation: false,
  formats: [],
};

const uniq = <T,>(xs: T[]) => [...new Set(xs)];
const num = (s: string | null): number | null => {
  if (s === null || s.trim() === "") return null;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 ? Math.round(n) : null;
};

/** Отмеченные грейды → сплошной диапазон: категория строится по диапазону `grade_min…grade_max`. */
export function gradeSpan(grades: string[]): TestGrade[] {
  const idx = grades.map((g) => TEST_GRADES.indexOf(g as TestGrade)).filter((i) => i >= 0);
  if (idx.length === 0) return [];
  return TEST_GRADES.slice(Math.min(...idx), Math.max(...idx) + 1);
}

/** URL → условия. Неизвестные значения отбрасываются, чтобы ручная правка ссылки не роняла экран. */
export function parseCriteria(p: URLSearchParams): Criteria {
  const trust = num(p.get("trust"));
  return {
    skills: uniq(p.getAll("skill").filter(Boolean)),
    profession: p.get("prof") || null,
    grades: gradeSpan(p.getAll("grade")),
    trust: trust !== null && trust >= 1 && trust <= 4 ? trust : null,
    fsp: p.get("fsp") === "1",
    confirmed: p.get("confirmed") === "1",
    cities: uniq(p.getAll("city").filter(Boolean)),
    salaryFrom: num(p.get("from")),
    salaryTo: num(p.get("to")),
    relocation: p.get("reloc") === "1",
    formats: uniq(p.getAll("format").filter((f) => (FORMATS as readonly string[]).includes(f))),
  };
}

/** Условия → параметры URL (порядок стабильный: одна и та же выдача — одна и та же ссылка). */
export function criteriaParams(c: Criteria, extra: Record<string, string | null | undefined> = {}): URLSearchParams {
  const p = new URLSearchParams();
  for (const s of c.skills) p.append("skill", s);
  if (c.profession) p.set("prof", c.profession);
  for (const g of c.grades) p.append("grade", g);
  if (c.trust !== null) p.set("trust", String(c.trust));
  if (c.fsp) p.set("fsp", "1");
  if (c.confirmed) p.set("confirmed", "1");
  for (const city of c.cities) p.append("city", city);
  if (c.salaryFrom !== null) p.set("from", String(c.salaryFrom));
  if (c.salaryTo !== null) p.set("to", String(c.salaryTo));
  if (c.relocation) p.set("reloc", "1");
  for (const f of c.formats) p.append("format", f);
  for (const [k, v] of Object.entries(extra)) if (v) p.set(k, v);
  return p;
}

/** Ключ условий: потребность пересоздаётся, только когда он меняется. */
export const criteriaKey = (c: Criteria): string => criteriaParams(c).toString();

/** Без навыков и профессии потребность не строится (`need_empty`): остальное — только сужает. */
export const hasSubject = (c: Criteria): boolean => c.skills.length > 0 || c.profession !== null;

export const isEmpty = (c: Criteria): boolean => criteriaKey(c) === "";

/** Сколько фильтров панели включено (для кнопки «Фильтры» на телефоне). */
export function filterCount(c: Criteria): number {
  return (
    (c.profession ? 1 : 0) +
    (c.grades.length ? 1 : 0) +
    (c.trust !== null ? 1 : 0) +
    (c.fsp ? 1 : 0) +
    (c.confirmed ? 1 : 0) +
    (c.cities.length ? 1 : 0) +
    (c.salaryFrom !== null || c.salaryTo !== null ? 1 : 0) +
    (c.relocation ? 1 : 0) +
    (c.formats.length ? 1 : 0)
  );
}

/** Условия → фильтры потребности. Навыки — обязательные: так их вес в категории выше. */
export function toNeedFilters(c: Criteria): SearchFilters {
  const f: SearchFilters = {};
  if (c.skills.length) f.skills_must = c.skills.map((slug) => ({ slug }));
  if (c.profession) f.professions = [c.profession];
  if (c.grades.length) {
    f.grade_min = c.grades[0] as Grade;
    f.grade_max = c.grades[c.grades.length - 1] as Grade;
  }
  if (c.trust !== null) f.min_trust = c.trust as TrustLevel;
  if (c.fsp) f.fsp_only = true;
  if (c.confirmed) f.only_confirmed = true;
  if (c.cities.length) f.cities = c.cities;
  if (c.salaryFrom !== null) f.salary_min = c.salaryFrom;
  if (c.salaryTo !== null) f.salary_max = c.salaryTo;
  if (c.relocation) f.relocation_ok = true;
  if (c.formats.length) f.formats = c.formats as WorkFormat[];
  return f;
}

/** Старая шкала грейдов резюме → тестовая (как `need_grades` на сервере). */
const TO_TEST: Record<string, TestGrade> = {
  intern: "junior",
  junior: "junior",
  junior_plus: "junior",
  middle: "middle",
  middle_plus: "middle",
  senior: "senior",
  lead: "senior",
};

function gradesOf(f: SearchFilters): TestGrade[] {
  if (!f.grade_min && !f.grade_max) return [];
  const lo = f.grade_min ? TO_TEST[f.grade_min] : "junior";
  const hi = f.grade_max ? TO_TEST[f.grade_max] : "senior";
  return gradeSpan([lo ?? "junior", hi ?? "senior"]);
}

/**
 * Разобранный текст (`/search/parse`) или фильтры потребности → условия поверх текущих: навыки
 * добавляются, названная роль становится профессией, остальные поля перекрывают прежние, если названы.
 */
export function mergeFilters(c: Criteria, f: SearchFilters): Criteria {
  const skills = uniq([...c.skills, ...(f.skills_must ?? []).map((s) => s.slug), ...(f.skills_nice ?? [])]);
  const prof = f.professions?.[0] ?? f.roles?.[0] ?? null;
  const grades = gradesOf(f);
  return {
    skills,
    profession: prof ?? c.profession,
    grades: grades.length ? grades : c.grades,
    trust: f.min_trust ?? c.trust,
    fsp: f.fsp_only ? true : c.fsp,
    confirmed: f.only_confirmed ? true : c.confirmed,
    cities: uniq([...c.cities, ...(f.cities ?? [])]),
    salaryFrom: f.salary_min ?? c.salaryFrom,
    salaryTo: f.salary_max ?? c.salaryTo,
    relocation: f.relocation_ok ? true : c.relocation,
    formats: uniq([...c.formats, ...(f.formats ?? [])]),
  };
}

export const fromFilters = (f: SearchFilters): Criteria => mergeFilters(EMPTY_CRITERIA, f);
