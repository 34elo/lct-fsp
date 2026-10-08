import { ApiError } from "@/api/mutator";

/** Тексты публичных вакансий и отклика (экран J1). */
export const JOBS_TEXT = {
  companyInterest: "Мне интересна компания",
  companyInterestOn: "Вы отметили компанию. Она увидит это в выдаче рядом с вашим профилем.",
  companyInterestOff: "Снять отметку",
  companyInterestHint: "Компания увидит, что вы заинтересованы, и вам станет проще получить интерес от неё. Контакты не раскрываются.",
  companyInterestError: "Не удалось сохранить отметку. Попробуйте ещё раз.",
  eyebrow: "Публичные вакансии",
  title: "Вакансии с открытой вилкой",
  lead: "Каждая вакансия показывает зарплату. Откликаться могут зарегистрированные кандидаты с подтверждённым email.",
  role: "Профессия",
  city: "Город",
  query: "Поиск по названию",
  anyRole: "Любая",
  loadError: "Не удалось загрузить вакансии.",
  empty: "Подходящих вакансий нет",
  emptyHint: "Сбросьте фильтры или загляните позже.",
  more: "Показать ещё",
  open: "Подробнее",
  back: "Все вакансии",
  notFound: "Вакансия не найдена или уже закрыта.",
  range: "Вилка в месяц",
  description: "О вакансии",
  skills: "Навыки",
  required: "обязательно",
  messageLabel: "Сообщение компании (по желанию)",
  messagePlaceholder: "Коротко о себе",
  contactsNote: "Откликаясь, вы открываете компании свои контакты. Остальные данные остаются скрытыми.",
  apply: "Откликнуться",
  sending: "Отправляем…",
  loginApply: "Войти и откликнуться",
  loginHint: "Вакансию видно всем, откликнуться можно после входа.",
  employerHint: "Откликаться могут только кандидаты.",
  unverifiedTitle: "Email не подтверждён",
  unverifiedHint: "Подтвердите email: после этого кнопка станет активной.",
  unverifiedAction: "Подтвердить email",
  sentTitle: "Отклик отправлен",
  sentHint: "Статус смотрите в разделе «Отклики».",
  toResponses: "Мои отклики",
  verified: "Проверена",
  employment: { full: "полная занятость", part: "частичная занятость", project: "проект", internship: "стажировка" } as Record<string, string>,
};

export function applyErrorText(err: unknown): string {
  if (!(err instanceof ApiError)) return "Не удалось отправить отклик. Попробуйте ещё раз.";
  switch (err.code) {
    case "already_applied":
      return "Вы уже откликались на эту вакансию: повторный отклик не нужен.";
    case "vacancy_not_found":
      return "Вакансия закрыта или не найдена.";
    case "company_in_stoplist":
      return "Эта компания в вашем стоп-листе.";
    case "application_limit_exceeded":
      return "Лимит откликов на сутки исчерпан. Попробуйте завтра.";
    case "consent_required":
      return "Сначала дайте согласие на обработку данных.";
  }
  if (err.status === 429) return "Слишком много запросов. Подождите немного.";
  return "Не удалось отправить отклик. Попробуйте ещё раз.";
}

export const isUnverified = (err: unknown): boolean => err instanceof ApiError && err.code === "email_not_verified";
