import { ApiError } from "@/api/mutator";

/** Коды ошибок привязки ФСП (api.md §2.2, fsp.md §4) человеческим языком. */
const MESSAGES: Record<string, string> = {
  fsp_not_found: "Не нашли участника с такими данными в ФСП.",
  fsp_already_linked: "Этот участник ФСП уже привязан к другому профилю. Мы отметили конфликт, его разберёт админ ФСП.",
  candidate_already_linked: "К вашему профилю уже привязан участник ФСП.",
  bad_email: "Проверьте email: в нём должна быть «@» и домен.",
  bad_phone: "Проверьте телефон: нужно не меньше 10 цифр.",
  validation_error: "Укажите email или телефон, под которым вы участвовали.",
  fsp_unavailable: "Реестр ФСП сейчас недоступен. Попробуйте позже.",
  consent_required: "Нужно согласие на обработку персональных данных.",
  sync_too_often: "Обновлять можно не чаще раза в 10 минут.",
  rate_limited: "Слишком много попыток. Подождите несколько минут.",
  fsp_not_linked: "Сначала привяжите профиль ФСП.",
  unauthorized: "Войдите заново и повторите.",
};

export function fspErrorText(code: string | null | undefined): string {
  return (code && MESSAGES[code]) || "Не получилось связаться с ФСП. Попробуйте ещё раз.";
}

export function fspApiError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 429 && !e.code) return MESSAGES.rate_limited;
    return fspErrorText(e.code);
  }
  return fspErrorText(null);
}

/** Тексты привязки ФСП через реестр (E39-28). */
export const FSP = {
  checking: "Проверяем привязку ФСП…",
  linkBtn: "Привязать ФСП",
  linking: "Ищем в базе ФСП…",
  linkHint: "Найдём вас в реестре ФСП по email аккаунта и телефону из профиля.",
  found: (by: "email" | "phone" | null | undefined) =>
    by === "phone" ? "Ваш телефон найден в базе ФСП." : "Ваш email найден в базе ФСП.",
  importing: "Подтягиваем достижения — это займёт несколько секунд.",
  imported: "Достижения и подтверждения обновлены.",
  linked: "ФСП подтверждена",
  linkedManual: "ФСП привязана без подтверждения",
  teams: "команды:",
  sync: "Обновить из ФСП",
  syncing: "Обновляем данные из ФСП…",
  notFound: "Ваших контактов нет в базе ФСП. Оставьте заявку — админ ФСП найдёт вас в протоколах.",
  formTitle: "Заявка на привязку ФСП",
  fullName: "ФИО, как в протоколах ФСП",
  email: "Email, под которым вы участвовали",
  phone: "Телефон, под которым вы участвовали",
  contactHint: "Достаточно одного: email или телефона.",
  event: "Мероприятие ФСП",
  eventHint: "Например: «Кубок России по продуктовому программированию, 2025».",
  send: "Отправить заявку",
  sending: "Отправляем…",
  cancel: "Отмена",
  pending: "Заявка отправлена. Админ ФСП проверит протоколы и привяжет профиль — статус появится здесь.",
  pendingEdit: "Изменить заявку",
  rejected: "Заявку отклонили",
  retry: "Подать заявку заново",
  since: (d: string) => `от ${new Date(d).toLocaleDateString("ru-RU")}`,
} as const;
