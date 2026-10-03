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

export const COMPANY_STATUS_LABEL: Record<string, string> = {
  pending: "На модерации",
  verified: "Проверена",
  rejected: "Отклонена",
  blocked: "Заблокирована",
};

export const COMPANY_STATUS_HINT: Record<string, string> = {
  pending: "Публиковать вакансии и отправлять офферы можно после проверки компании администратором ФСП.",
  verified: "Компания проверена: можно публиковать вакансии и отправлять офферы.",
  rejected: "Проверка не пройдена. Исправьте данные компании и обратитесь к администратору.",
  blocked: "Компания заблокирована.",
};

export const QUALITY_HINT: Record<string, string> = {
  leadership: "подтверждается капитанством и руководством командами",
  teamwork: "командные соревнования, общие репозитории",
  results: "призовые места и измеримые результаты",
  growth: "заметный рост навыков за последние месяцы",
};

export const LEVEL_WORD = ["", "базовый", "рабочий", "уверенный", "эксперт"] as const;

/** Понятный текст по `code` Problem Details для компаний и вакансий. */
export function vacancyErrorText(err: unknown, fallback = "Не удалось выполнить действие. Попробуйте ещё раз."): string {
  const code = (err as { code?: string } | null)?.code;
  switch (code) {
    case "company_exists":
      return "Компания уже зарегистрирована.";
    case "company_not_found":
      return "Сначала зарегистрируйте компанию.";
    case "company_not_verified":
      return "Компания ещё не прошла проверку: опубликовать вакансию пока нельзя. Черновик сохранён.";
    case "no_required_skills":
      return "Добавьте хотя бы один обязательный навык.";
    case "invalid_grade_range":
      return "Минимальный грейд не может быть выше максимального.";
    case "invalid_salary_range":
      return "Верхняя граница вилки не может быть меньше нижней.";
    case "unknown_skill":
      return "Один из навыков не найден в справочнике.";
    case "duplicate_skill":
      return "Навык указан дважды.";
    case "invalid_status":
      return "В текущем статусе вакансию изменить нельзя.";
    case "vacancy_not_found":
      return "Вакансия не найдена.";
    default:
      return fallback;
  }
}
