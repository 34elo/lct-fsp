import { ApiError } from "@/api/mutator";
import type { FamilySpec, Kind, Param } from "@/api/model";
import { T } from "./text";

export type VarType = "range" | "values" | "expr";
export interface VarRow {
  id: number;
  name: string;
  type: VarType;
  min: string;
  max: string;
  step: string;
  list: string;
  expr: string;
}

export interface FormState {
  title: string;
  skill: string;
  level: number;
  timeLimit: string;
  kind: Exclude<Kind, "chain">;
  stem: string;
  vars: VarRow[];
  answer: string;
  precision: string;
  options: string;
  correct: string;
  lines: string;
  bugLines: string;
  steps: string;
  actions: string;
  rubric: string;
}

export const KINDS: FormState["kind"][] = ["exact", "estimate", "choice", "find_bug", "order", "sjt", "open"];

export const emptyVar = (id: number): VarRow => ({ id, name: "", type: "range", min: "", max: "", step: "", list: "", expr: "" });

export const initialForm = (): FormState => ({
  title: "",
  skill: "",
  level: 3,
  timeLimit: "90",
  kind: "exact",
  stem: "",
  vars: [],
  answer: "",
  precision: "0",
  options: "",
  correct: "",
  lines: "",
  bugLines: "",
  steps: "",
  actions: "",
  rubric: "",
});

const rows = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
const numOrNull = (s: string) => {
  const t = s.trim().replace(",", ".");
  if (t === "") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

function parseList(s: string): (number | string)[] {
  return s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .map((x) => (Number.isFinite(Number(x.replace(",", "."))) ? Number(x) : x));
}

/** Форма → `FamilySpec`. Пустой ключ не отправляем: core попросит черновик у LLM. */
export function buildSpec(f: FormState): FamilySpec {
  const params: Record<string, Param> = {};
  const derived: Record<string, string> = {};
  for (const v of f.vars) {
    const name = v.name.trim();
    if (!name) continue;
    if (v.type === "expr") derived[name] = v.expr.trim();
    else if (v.type === "values") params[name] = { values: parseList(v.list) };
    else params[name] = { min: numOrNull(v.min), max: numOrNull(v.max), step: numOrNull(v.step) };
  }
  const spec: FamilySpec = {
    title: f.title.trim(),
    kind: f.kind,
    skill: f.skill.trim(),
    level: f.level,
    stem: f.stem,
    params,
    derived,
  };
  const t = numOrNull(f.timeLimit);
  if (t !== null) spec.time_limit_s = t;
  switch (f.kind) {
    case "exact":
    case "estimate":
      if (f.answer.trim()) spec.answer = f.answer.trim();
      if (f.kind === "exact") {
        const p = numOrNull(f.precision);
        if (p !== null) spec.precision = p;
      }
      break;
    case "choice": {
      spec.options = rows(f.options);
      const c = numOrNull(f.correct);
      if (c !== null) spec.correct = c - 1;
      break;
    }
    case "find_bug": {
      spec.lines = rows(f.lines);
      const bl = parseList(f.bugLines).filter((x): x is number => typeof x === "number");
      if (bl.length) spec.bug_lines = bl;
      break;
    }
    case "order":
      spec.steps = rows(f.steps);
      break;
    case "sjt":
      spec.actions = rows(f.actions).map((line) => {
        const [text, score] = line.split("|").map((x) => x.trim());
        const s = score === undefined ? null : numOrNull(score);
        return s === null ? { text: text ?? "" } : { text: text ?? "", score: s };
      });
      break;
    case "open":
      spec.rubric = rows(f.rubric);
      break;
  }
  return spec;
}

export function localErrors(f: FormState): Record<string, string> {
  const e: Record<string, string> = {};
  if (!f.title.trim()) e.title = T.errors.local.title;
  if (!f.skill.trim()) e.skill = T.errors.local.skill;
  if (f.stem.trim().length < 10) e.stem = T.errors.local.stem;
  return e;
}

export interface ProblemView {
  code: string | undefined;
  message: string;
  details: string[];
}

/** Ошибка POST /families → текст и перечень из `errors[]` (422 autocheck_failed, key_required). */
export function problemView(err: unknown): ProblemView {
  if (!(err instanceof ApiError)) return { code: undefined, message: T.errors.generic, details: [] };
  const body = (err.body ?? {}) as { errors?: { field?: string; message?: string }[] | null };
  const details = (body.errors ?? []).map((x) => x.message ?? "").filter(Boolean);
  switch (err.code) {
    case "autocheck_failed":
      return { code: err.code, message: T.errors.autocheck, details };
    case "key_required":
      return { code: err.code, message: T.errors.keyRequired, details: (body.errors ?? []).map((x) => x.field ?? "").filter(Boolean) };
    case "unknown_skill":
      return { code: err.code, message: T.errors.unknownSkill, details: [] };
    case "company_not_found":
      return { code: err.code, message: T.errors.noCompany, details: [] };
  }
  if (err.status === 403) return { code: err.code, message: T.errors.forbidden, details: [] };
  return { code: err.code, message: T.errors.generic, details };
}

/** Невыполненные пороги → причины человеческим языком через запятую. */
export function admissionReasons(failed: string[]): string {
  return failed.map((x) => T.queue.reasons[x] ?? x).join(", ");
}
