/** Чистые функции экрана теста: форма ответа по `kind`, таймер, разбор стема, доли по навыкам. */

export interface TestItem {
  kind: string;
  stem: string;
  options?: string[] | null;
}

/** Значение ответа в форме: строка (exact/estimate), индекс (choice), список номеров (find_bug, order, sjt). */
export type AnswerValue = string | number | number[] | null;

export function initialAnswer(item: TestItem): AnswerValue {
  switch (item.kind) {
    case "exact":
    case "estimate":
      return "";
    case "choice":
      return null;
    case "find_bug":
      return [];
    case "order":
    case "sjt":
      return (item.options ?? []).map((_, i) => i);
    default:
      return null;
  }
}

export function isAnswered(item: TestItem, v: AnswerValue): boolean {
  switch (item.kind) {
    case "exact":
    case "estimate":
      return typeof v === "string" && v.trim() !== "";
    case "choice":
      return typeof v === "number";
    case "find_bug":
      return Array.isArray(v) && v.length > 0;
    case "order":
    case "sjt":
      return Array.isArray(v) && v.length > 0;
    default:
      return false;
  }
}

/** Число из «3 000 000», «1,5e6», «10^5». Пусто или мусор → null (сервер даст 0 баллов). */
export function parseNumber(s: string): number | null {
  const t = s.trim().replace(/\s+/g, "").replace(",", ".");
  const pow = /^10\^(-?\d+)$/.exec(t);
  const n = pow ? Math.pow(10, Number(pow[1])) : Number(t);
  return t !== "" && Number.isFinite(n) ? n : null;
}

/** Что уходит в `answer`: exact — строка как есть, estimate — число, остальное — индексы. */
export function toPayload(item: TestItem, v: AnswerValue): unknown {
  if (item.kind === "estimate") return typeof v === "string" ? parseNumber(v) : null;
  if (item.kind === "exact") return typeof v === "string" ? v.trim() : null;
  if (item.kind === "find_bug") return Array.isArray(v) ? [...v].sort((a, b) => a - b) : [];
  return v;
}

export interface CodeLine {
  no: number;
  text: string;
}

const LINE = /^\s*(\d+) \| ?(.*)$/;

/** `find_bug`: условие и листинг приходят одним текстом («NN | код»); номера строк — ответ. */
export function parseListing(stem: string): { prose: string; lines: CodeLine[] } {
  const rows = stem.split("\n");
  const first = rows.findIndex((r) => LINE.test(r));
  if (first < 0) return { prose: stem, lines: [] };
  const lines: CodeLine[] = [];
  for (const r of rows.slice(first)) {
    const m = LINE.exec(r);
    if (m) lines.push({ no: Number(m[1]), text: m[2] ?? "" });
  }
  return { prose: rows.slice(0, first).join("\n").trim(), lines };
}

/** Код в условии `exact`: блок после пустой строки показываем моноширинным. */
/** В условии есть GFM-таблица (строка-разделитель `| --- |`): такое условие показываем Markdown-ом целиком. */
export function hasTable(stem: string): boolean {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/m.test(stem);
}

export function splitStem(stem: string): { prose: string; code: string | null } {
  if (hasTable(stem)) return { prose: stem, code: null };
  const at = stem.indexOf("\n\n");
  if (at < 0) return { prose: stem, code: null };
  return { prose: stem.slice(0, at).trim(), code: stem.slice(at + 2).trim() || null };
}

export function toggleLine(v: number[], no: number): number[] {
  return v.includes(no) ? v.filter((x) => x !== no) : [...v, no].sort((a, b) => a - b);
}

/** Переносит элемент с позиции `from` на позицию `to`, остальные сдвигаются. Вне границ — без изменений. */
export function moveTo(list: number[], from: number, to: number): number[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const out = [...list];
  out.splice(to, 0, out.splice(from, 1)[0]!);
  return out;
}

/** Сдвиг элемента списка на `delta` (−1 вверх, +1 вниз). Выход за границы — без изменений. */
export function move(list: number[], at: number, delta: -1 | 1): number[] {
  const to = at + delta;
  if (to < 0 || to >= list.length) return list;
  const out = [...list];
  [out[at], out[to]] = [out[to]!, out[at]!];
  return out;
}

export function formatClock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Шаги `chain` из ответа `next`: неизвестная форма отбрасывается. */
export function chainSteps(steps: unknown): TestItem[] {
  if (!Array.isArray(steps)) return [];
  return steps
    .filter((s): s is Record<string, unknown> => !!s && typeof s === "object")
    .map((s) => ({
      kind: typeof s.kind === "string" ? s.kind : "choice",
      stem: typeof s.stem === "string" ? s.stem : "",
      options: Array.isArray(s.options) ? (s.options as unknown[]).map(String) : null,
    }));
}

export interface SkillRow {
  skill: string;
  items: number;
  share: number;
}

export const HOLDS_SHARE = 0.6;

/** `by_skill` приходит как свободный словарь: берём только корректные строки. */
export function skillRows(raw: unknown): SkillRow[] {
  if (!Array.isArray(raw)) return [];
  const rows: SkillRow[] = [];
  for (const r of raw) {
    if (!r || typeof r !== "object") continue;
    const { skill, items, share } = r as Record<string, unknown>;
    if (typeof skill === "string" && typeof share === "number") {
      rows.push({ skill, items: typeof items === "number" ? items : 0, share });
    }
  }
  return rows;
}

export const holds = (share: number): boolean => share >= HOLDS_SHARE;

/** Подтверждение действует 12 месяцев с даты завершения. */
export function validUntil(finishedAt: string | null | undefined): string | null {
  if (!finishedAt) return null;
  const d = new Date(finishedAt);
  if (Number.isNaN(d.getTime())) return null;
  d.setUTCFullYear(d.getUTCFullYear() + 1);
  return d.toISOString();
}

export const isFuture = (iso: string, now = Date.now()): boolean => new Date(iso).getTime() > now;

/** Стек: нижний регистр, без пробелов по краям и дублей, не больше 30. */
export function addStack(stack: string[], raw: string): string[] {
  const s = raw.trim().toLowerCase();
  if (!s || stack.includes(s) || stack.length >= 30) return stack;
  return [...stack, s];
}

export function salaryError(from: string, to: string): boolean {
  const a = Number(from);
  const b = Number(to);
  return from !== "" && to !== "" && Number.isFinite(a) && Number.isFinite(b) && a > b;
}

export interface AnswerRow {
  responseId: string;
  seq: number;
  skill: string;
  score: number;
}

/** `result.answers` приходит свободным словарём: берём корректные строки, где набрано не всё. */
export function missedAnswers(raw: unknown): AnswerRow[] {
  if (!Array.isArray(raw)) return [];
  const rows: AnswerRow[] = [];
  for (const r of raw) {
    if (!r || typeof r !== "object") continue;
    const { response_id, seq, skill, score } = r as Record<string, unknown>;
    if (typeof response_id === "string" && typeof seq === "number" && typeof score === "number" && score < 1) {
      rows.push({ responseId: response_id, seq, skill: typeof skill === "string" ? skill : "", score });
    }
  }
  return rows.sort((a, b) => a.seq - b.seq);
}

/** Первый шаг пути кандидата после согласий (E35-2a): опрос, из него — тест. */
export const PATH_START = "/me/assessment";

export type PathStep = { kind: "survey" | "test"; to: string } | { kind: "continue"; to: string };

/**
 * Чего не хватает кандидату на главном пути (E35-2a): нет опроса → опрос; есть идущая попытка →
 * продолжить её; нет завершённого теста → тест. Всё пройдено — `null` (баннер не нужен).
 */
export function pathStep(history: {
  surveys: unknown[];
  attempts: { id: string; status: string }[];
}): PathStep | null {
  if (history.surveys.length === 0) return { kind: "survey", to: PATH_START };
  const active = history.attempts.find((a) => a.status === "active");
  if (active) return { kind: "continue", to: `/me/assessment/attempts/${active.id}` };
  if (!history.attempts.some((a) => a.status === "passed" || a.status === "failed")) return { kind: "test", to: PATH_START };
  return null;
}

/* ---------- Результат v2 (E38-5): шкала 0–100 для GradeScale и TypeBar ---------- */

const GRADE_ORDER = ["junior", "middle", "senior"] as const;

/** Пороги θ грейдов (assessment.md §2): Junior −1, Middle 0, Senior 1. */
export const GRADE_CUTS: Record<string, number> = { junior: -1, middle: 0, senior: 1 };

/**
 * θ → балл шкалы 0–100: 55 + 25·θ. Пороги ложатся на полосы `GradeScale` по умолчанию:
 * Junior −1 → 30, Middle 0 → 55, Senior 1 → 80.
 */
export function toScale(theta: number): number {
  return Math.round(Math.max(0, Math.min(100, 55 + 25 * theta)));
}

/** Погрешность θ (`se`) в баллах шкалы. Нет или не число — `undefined`. */
export function seScale(se: number | null | undefined): number | undefined {
  return typeof se === "number" && Number.isFinite(se) && se > 0 ? Math.round(25 * se) : undefined;
}

export const nextGrade = (g: string): string | null => GRADE_ORDER[GRADE_ORDER.indexOf(g as never) + 1] ?? null;

export function lowerGrade(g: string): string | null {
  const i = GRADE_ORDER.indexOf(g as never);
  return i > 0 ? GRADE_ORDER[i - 1]! : null;
}

/** Порог, с которым сравниваем результат: подтверждён — следующий грейд (Senior — свой), нет — заявленный. */
export function thresholdGrade(grade: string | null | undefined, declared: string): string {
  return grade ? (nextGrade(grade) ?? grade) : declared;
}

export const SKILL_TYPES = ["fundamental", "hard", "thinking", "business", "soft", "experience"] as const;

export interface TypeRow {
  type: string;
  value: number;
}

/** `theta_by_type` → строки TypeBar в порядке типов; неизвестные типы и не-числа отбрасываются. */
export function typeRows(raw: Record<string, number> | null | undefined): TypeRow[] {
  if (!raw || typeof raw !== "object") return [];
  return SKILL_TYPES.filter((t) => typeof raw[t] === "number" && Number.isFinite(raw[t])).map((t) => ({ type: t, value: toScale(raw[t]!) }));
}

/** Последний опрос по профессии (по `created_at`): заявленный стек и вилка для «не подтверждён». */
export function latestSurvey<S extends { profession?: string | null; created_at?: string | null }>(surveys: S[], profession: string): S | null {
  return (
    surveys
      .filter((s) => s.profession === profession)
      .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))[0] ?? null
  );
}

export type Verdict = "ok" | "part" | "bad";
export const verdict = (score: number): Verdict => (score >= 1 ? "ok" : score > 0 ? "part" : "bad");

export interface ReviewGroup<R extends { type: string; score: number }> {
  type: string;
  rows: R[];
  done: number;
}

/** Группировка по типам навыков в порядке `SKILL_TYPES`; неизвестные типы — в конец, пустые группы не нужны. */
export function groupByType<R extends { type: string; score: number }>(rows: R[]): ReviewGroup<R>[] {
  const known: string[] = [...SKILL_TYPES];
  const types = [...new Set(rows.map((r) => r.type))].sort((a, b) => (known.indexOf(a) + 1 || 99) - (known.indexOf(b) + 1 || 99));
  return types.map((t) => {
    const list = rows.filter((r) => r.type === t);
    return { type: t, rows: list, done: list.filter((r) => r.score >= 1).length };
  });
}

/** «Что подтянуть»: навыки с неполным баллом, сначала самые слабые; возвращает долю набранного. */
export function weakSkills(rows: { skill: string; score: number }[]): { skill: string; share: number; missed: number }[] {
  const acc = new Map<string, number[]>();
  for (const r of rows) acc.set(r.skill, [...(acc.get(r.skill) ?? []), r.score]);
  return [...acc.entries()]
    .map(([skill, v]) => ({ skill, share: v.reduce((a, b) => a + b, 0) / v.length, missed: v.filter((x) => x < 1).length }))
    .filter((x) => x.missed > 0)
    .sort((a, b) => a.share - b.share || a.skill.localeCompare(b.skill));
}

const HIDE_KEY = "fsp.assessment.review.hideExplain";

/** Переключатель «Скрыть объяснения» запоминается в браузере; без хранилища — выключен. */
export function loadHideExplain(): boolean {
  try {
    return localStorage.getItem(HIDE_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveHideExplain(v: boolean): void {
  try {
    if (v) localStorage.setItem(HIDE_KEY, "1");
    else localStorage.removeItem(HIDE_KEY);
  } catch {
    /* хранилище недоступно — переключатель работает до перезагрузки */
  }
}
