import type { ExplanationItem } from "@/api/model";

export const FORMAT_LABEL: Record<string, string> = { office: "Офис", hybrid: "Гибрид", remote: "Удалённо" };

export const EMPLOYMENT_LABEL: Record<string, string> = {
  full: "Полная занятость",
  part: "Частичная",
  project: "Проект",
  internship: "Стажировка",
};

export const VACANCY_STATUS_LABEL: Record<string, string> = { draft: "Черновик", published: "Опубликована", closed: "Закрыта" };

export const SORT_LABEL = { match: "По совпадению", trust: "По доверию", fresh: "По свежести" } as const;

export const SEARCH_STATUS_LABEL: Record<string, string> = {
  active: "Активно ищет",
  open: "Открыт к предложениям",
};

/** Источник подтверждения навыка — то, чем он подкреплён (не «имя репозитория»). */
export const SOURCE_SHORT: Record<string, string> = {
  fsp: "ФСП",
  github: "GitHub",
  test: "Тест",
  resume: "Резюме",
  self: "Заявлено",
  ai_interview: "Интервью",
  codeforces: "Codeforces",
};

export function rub(n: number): string {
  return `${n.toLocaleString("ru-RU")} ₽`;
}

export function percent(score: number): number {
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

/** Плюсы и минусы объяснения: `plus` зелёным, остальное (`warn`/`minus`) предупреждением. */
export function splitExplanation(items: ExplanationItem[]) {
  return {
    pluses: items.filter((i) => i.kind === "plus"),
    others: items.filter((i) => i.kind !== "plus"),
  };
}
