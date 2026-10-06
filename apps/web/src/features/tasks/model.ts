/** Чистая логика регулярных заданий: форма ответа по типу и статусы. */

export type TaskItem = { kind?: string; stem?: string; options?: string[] | null; steps?: TaskItem[]; [k: string]: unknown };

/** Состояние поля ответа: зависит от типа задания. */
export type AnswerState = string | number | null | number[] | AnswerState[];

export function initialAnswer(item: TaskItem): AnswerState {
  switch (item.kind) {
    case "choice":
      return null;
    case "find_bug":
      return [];
    case "order":
    case "sjt":
      return (item.options ?? []).map((_, i) => i);
    case "chain":
      return (item.steps ?? []).map(initialAnswer);
    default:
      return "";
  }
}

/** Ответ готов к отправке (кнопка активна). */
export function isReady(item: TaskItem, s: AnswerState): boolean {
  switch (item.kind) {
    case "choice":
      return typeof s === "number";
    case "find_bug":
      return Array.isArray(s) && s.length > 0;
    case "order":
    case "sjt":
      return Array.isArray(s) && s.length > 0;
    case "chain":
      return Array.isArray(s) && (item.steps ?? []).every((st, i) => isReady(st, (s as AnswerState[])[i] ?? null));
    default:
      return typeof s === "string" && s.trim().length > 0;
  }
}

/** Значение для API: числа — числом, остальное — как есть. */
export function toAnswer(item: TaskItem, s: AnswerState): unknown {
  switch (item.kind) {
    case "exact":
    case "estimate": {
      const t = String(s ?? "").trim();
      return /^-?\d+([.,]\d+)?$/.test(t) ? Number(t.replace(",", ".")) : t;
    }
    case "find_bug":
      return [...(s as number[])].sort((a, b) => a - b);
    case "chain":
      return (item.steps ?? []).map((st, i) => toAnswer(st, (s as AnswerState[])[i] ?? null));
    case "open":
      return String(s ?? "").trim();
    default:
      return s;
  }
}

/** Перестановка: сдвиг элемента на позиции i в сторону d (−1 / +1). */
export function moveItem(order: number[], i: number, d: -1 | 1): number[] {
  const j = i + d;
  if (j < 0 || j >= order.length) return order;
  const out = [...order];
  [out[i], out[j]] = [out[j]!, out[i]!];
  return out;
}

export type CandTask = { id: string; kind: string; answer_until?: string | null; submitted?: boolean; score?: number | null };

export const isClosed = (t: Pick<CandTask, "answer_until">, now = Date.now()) => !!t.answer_until && new Date(t.answer_until).getTime() < now;

export type CandStatus = "new" | "accepted" | "waiting" | "scored" | "closed";

export function candStatus(t: CandTask, now = Date.now()): CandStatus {
  if (t.submitted) {
    if (t.score != null) return "scored";
    return t.kind === "open" ? "waiting" : "accepted";
  }
  return isClosed(t, now) ? "closed" : "new";
}

export const inTab = (t: CandTask, tab: string) => (tab === "mine" ? !!t.submitted : !t.submitted);

export const pct = (v: number) => Math.round(v * 100);
