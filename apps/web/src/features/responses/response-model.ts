/** Чистая логика списков откликов: вкладки и счётчики. */

export type CandTab = "all" | "waiting" | "invited" | "closed";
export type EmpTab = "all" | "new" | "invited" | "rejected";

const WAITING = ["sent", "viewed"];
const INVITED = ["accepted", "interview", "hired"];

export function candTabOf(status: string): Exclude<CandTab, "all"> {
  if (WAITING.includes(status)) return "waiting";
  if (INVITED.includes(status)) return "invited";
  return "closed";
}

export function empTabOf(status: string): Exclude<EmpTab, "all"> {
  if (WAITING.includes(status)) return "new";
  if (INVITED.includes(status)) return "invited";
  return "rejected";
}

/** Вкладки кандидата: счётчики по группам, «Все» — всё. */
export function countBy<T extends { status: string }>(items: T[], key: (s: string) => string): Record<string, number> {
  const out: Record<string, number> = { all: items.length };
  for (const i of items) out[key(i.status)] = (out[key(i.status)] ?? 0) + 1;
  return out;
}

export function filterBy<T extends { status: string }>(items: T[], tab: string, key: (s: string) => string): T[] {
  return tab === "all" ? items : items.filter((i) => key(i.status) === tab);
}
