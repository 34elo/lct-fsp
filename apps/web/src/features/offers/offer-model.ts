/** Чистая логика формы оффера: разбор вилки и проверки. Используют страница и модалка оффера. */

/** «230 000» → 230000; пусто или не число → null. */
export function parseRub(s: string): number | null {
  if (s.trim() === "") return null;
  const n = Math.round(Number(s.replace(/\s/g, "")));
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Показать число с разрядами: 230000 → «230 000» (для поля ввода). */
export function groupDigits(s: string): string {
  const d = s.replace(/\D/g, "");
  return d.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

export type RangeProblem = "missing" | "inverted" | null;

export function rangeProblem(lo: number | null, hi: number | null): RangeProblem {
  if (lo === null || hi === null) return "missing";
  return hi < lo ? "inverted" : null;
}

/** «Слишком широкая вилка»: (до − от) / от > 0.5. */
export function isWideRange(lo: number | null, hi: number | null): boolean {
  return lo !== null && hi !== null && lo > 0 && hi >= lo && (hi - lo) / lo > 0.5;
}

/** Можно ли отправить: вилка корректна, есть вакансия или название. */
export function canSendOffer(opts: { lo: number | null; hi: number | null; vacancyId: string; title: string }): boolean {
  return rangeProblem(opts.lo, opts.hi) === null && (opts.vacancyId !== "" || opts.title.trim() !== "");
}
