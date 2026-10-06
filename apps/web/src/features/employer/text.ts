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

/** Уровень соревнования ФСП в строке протокола. */
export const FSP_LEVEL_LABEL: Record<string, string> = {
  regional: "региональный этап",
  interregional: "межрегиональный этап",
  national: "всероссийский этап",
  international: "международный этап",
};

/** Тексты экрана A (поиск) и E2 («текст → чипсы»). */
export const SEARCH_TEXT = {
  title: "Поиск кандидатов",
  shortlistTitle: (t: string) => `Подборка: ${t}`,
  anon: "Карточки анонимны: имя, контакты и компании открываются после принятия оффера.",
  queryLabel: "Кого ищете",
  queryPlaceholder: "Например: бэкендер на Python, высоконагруженный API, удалёнка, до 220 тыс",
  find: "Найти",
  parsing: "Разбираем запрос…",
  recognized: "Распознано",
  approxHint: "«~» — понято приблизительно, учитываем смежные навыки",
  parseFailed: "Не удалось разобрать запрос. Задайте фильтры слева.",
  nothingRecognized: "Ничего не распознали: уточните запрос или задайте фильтры слева.",
  filters: "Фильтры",
  reset: "Сбросить",
  vacancy: "Вакансия (подборка)",
  vacancyNone: "Без вакансии: свободный поиск",
  role: "Роль",
  any: "Любая",
  trust: "Минимальный уровень доверия",
  trustAny: "Любой",
  trustHint: "Для ключевых навыков запроса",
  fsp: "Подтверждение ФСП",
  fspOnly: "Только с подтверждением ФСП",
  activeOnly: "Только активно ищут",
  format: "Формат",
  grade: "Грейд",
  budget: "Бюджет, ₽ в месяц",
  budgetAny: "любой",
  skills: "Обязательные навыки",
  addSkill: "Добавить навык…",
  sort: "Сортировка",
  found: (n: number) => `${n} ${plural(n, "анонимный профиль", "анонимных профиля", "анонимных профилей")}`,
  searching: "Ищем…",
  empty: "Никого не нашли",
  emptyHint: "Ослабьте фильтры или уберите обязательные навыки.",
  failed: "Не удалось загрузить выдачу",
  more: "Показать ещё",
  loadingMore: "Загружаем…",
} as const;

export const BUDGET_MIN = 50_000;
export const BUDGET_MAX = 400_000;
export const BUDGET_STEP = 10_000;

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

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

/** Тексты экрана E4 (подборка по вакансии). */
export const SHORTLIST_TEXT = {
  kicker: "Подборка по вакансии",
  title: "Подборка",
  list: "Подборка кандидатов",
  sort: "Сортировка",
  byInterest: "С учётом интереса кандидата",
  byMatch: "Только по соответствию",
  mutualHint: "Порядок учитывает и соответствие, и интерес кандидата: кто с большей вероятностью ответит «да», поднимается выше. Так меньше отказов и быстрее найм.",
  count: (n: number, fsp: number) => `${n} ${plural(n, "кандидат", "кандидата", "кандидатов")}${fsp > 0 ? `, из них ${fsp} с подтверждением ФСП` : ""}`,
  offer: "Оффер",
  expand: (p: string) => `Показать обоснование: ${p}`,
  collapse: (p: string) => `Скрыть обоснование: ${p}`,
  why: "Почему подходит",
  care: "Что учесть",
  noWhy: "Явных совпадений не найдено.",
  noCare: "Замечаний нет.",
  noFsp: "Результатов ФСП нет",
  interest: (l: string) => `Интерес кандидата: ${l === "high" ? "высокий" : l === "medium" ? "средний" : "низкий"}`,
  footnote: (n: number) => `Развёрнутое обоснование всегда открыто для первых ${n}. Для остальных — по стрелке справа.`,
  more: "Показать ещё",
  empty: "Подходящих кандидатов пока нет",
  emptyHint: "Снизьте минимальный уровень навыков или переведите часть навыков в желательные.",
  failed: "Не удалось загрузить подборку",
  notFound: "Вакансия не найдена",
  toVacancies: "К вакансиям",
};
