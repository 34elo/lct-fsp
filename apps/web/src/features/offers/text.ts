import { ApiError } from "@/api/mutator";

export const OFFER_STATUS_LABEL: Record<string, string> = {
  sent: "Отправлен",
  viewed: "Просмотрен",
  accepted: "Принят",
  interview: "Интервью",
  hired: "Нанят",
  not_hired: "Не нанят",
  declined: "Отклонён",
  expired: "Истёк",
  withdrawn: "Отозван",
};

/** Тон бейджа статуса (токены, без своих цветов). */
export function statusTone(status: string): string {
  switch (status) {
    case "accepted":
    case "hired":
      return "bg-success-bg text-success";
    case "declined":
    case "not_hired":
      return "bg-error-bg text-error";
    case "expired":
    case "withdrawn":
      return "border border-hairline text-muted";
    default:
      return "bg-tint-50 text-brand-deep dark:text-brand-mid";
  }
}

export const DECLINE_LABEL: Record<string, string> = {
  low_salary: "Мало денег",
  wrong_stack: "Не тот стек",
  wrong_format: "Не подходит формат",
  wrong_grade: "Не тот уровень",
  not_looking: "Не ищу сейчас",
  other: "Другое",
};

export const ACTOR_LABEL: Record<string, string> = { company: "Компания", candidate: "Кандидат", system: "Система" };

export const ACCEPT_LABEL = { low: "низкая", medium: "средняя", high: "высокая" } as const;

export const ACTIVE_STATUSES = ["sent", "viewed", "accepted", "interview"];

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function dateOnly(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
}

export function daysLeft(iso: string): number {
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000));
}

/** Понятный текст по машинному `code` Problem Details (api.md, офферы). */
export function offerErrorText(err: unknown, fallback = "Не удалось выполнить действие. Попробуйте ещё раз."): string {
  if (!(err instanceof ApiError)) return fallback;
  switch (err.code) {
    case "salary_range_required":
      return "Укажите вилку зарплаты: оффер без вилки отправить нельзя.";
    case "invalid_salary_range":
      return "Верхняя граница вилки не может быть меньше нижней.";
    case "offer_exists":
      return "Оффер этому кандидату по этой вакансии уже отправлен.";
    case "idempotency_key_reused":
      return "Этот запрос уже использован для другого оффера. Обновите страницу и повторите.";
    case "offer_limit_exceeded":
      return "Лимит офферов на сутки исчерпан. Попробуйте позже.";
    case "candidate_offer_limit_exceeded":
      return "Этот кандидат уже получил много офферов за сутки. Попробуйте позже.";
    case "company_not_verified":
      return "Компания ещё не прошла верификацию, отправка офферов недоступна.";
    case "vacancy_not_published":
      return "Вакансия не опубликована. Опубликуйте её и повторите.";
    case "vacancy_not_found":
      return "Вакансия не найдена.";
    case "candidate_not_found":
      return "Кандидат не найден или скрыл анкету.";
    case "offer_expired":
      return "Срок оффера истёк.";
    case "invalid_transition":
      return "Это действие уже недоступно: статус оффера изменился.";
    case "offer_closed":
      return "Переписка по этому офферу закрыта.";
    case "empty_message":
      return "Сообщение не может быть пустым.";
    case "contacts_not_revealed":
      return "Контакты откроются после принятия оффера.";
    case "offer_not_found":
      return "Оффер не найден.";
  }
  if (err.status === 429) return "Слишком много запросов. Подождите немного и повторите.";
  if (err.status === 409) return "Состояние оффера изменилось. Обновите страницу.";
  if (err.status === 422) return "Проверьте заполнение формы.";
  return fallback;
}

/** Тексты экрана E5 (мои офферы, канбан). */
export const BOARD_TEXT = {
  title: "Мои офферы",
  subtitle: (n: number) => `Отправлено офферов: ${n}. Колонки — статусы, в «Закрыто» отказы, истёкшие и отозванные.`,
  columns: { sent: "Отправлен", viewed: "Просмотрен", interview: "Интервью", accepted: "Принят", hired: "Нанят", closed: "Закрыто" },
  tabs: "Статусы офферов",
  count: (n: number) => `Карточек: ${n}`,
  emptyColumn: "Пока пусто",
  deleted: "Кандидат удалил анкету",
  reason: (r: string) => `Отклонён · ${r}`,
  replyBy: (d: string) => `ответ до ${d}`,
  yourTurn: "Ждёт вашего ответа",
  kpiViewed: "Просмотрено",
  kpiAccepted: "Приняли",
  kpiHired: "Нанято",
  loadError: "Не удалось загрузить офферы",
  empty: "Офферов пока нет",
  emptyHint: "Найдите кандидата в поиске и отправьте первый оффер с вилкой.",
  toSearch: "Перейти к поиску",
  declinesTitle: "Почему отказываются",
  declinesTotal: (n: number) => `отказов: ${n}`,
  hintLabel: "Что подсказывает система",
  hintDefault: "Откройте вакансию и сверьте требования с тем, что ищут кандидаты.",
  hint: {
    wrong_stack: "Уточните обязательные навыки: если стек не жёсткий, переведите часть навыков в «желательные» и укажите смежные.",
    low_salary: "Нижняя граница вилки ниже ожиданий кандидатов. Живая подсказка в окне оффера покажет это до отправки.",
    wrong_format: "Проверьте форматы работы в вакансии: удалённый или гибридный формат расширяет круг кандидатов.",
    wrong_grade: "Сверьте диапазон грейдов в вакансии с тем, кого вы приглашаете.",
    not_looking: "Кандидаты со статусом «не ищу» откликаются реже: ищите среди активных.",
  } as Record<string, string>,
  openVacancies: "Открыть вакансии",
};
