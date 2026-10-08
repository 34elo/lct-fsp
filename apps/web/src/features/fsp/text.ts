import { ApiError } from "@/api/mutator";

/** Коды ошибок привязки ФСП (api.md §2.2, fsp.md) человеческим языком. */
const MESSAGES: Record<string, string> = {
  fsp_not_found: "Не нашли участника с такими данными в ФСП. Проверьте ID или email.",
  fsp_already_linked: "Этот участник ФСП уже привязан к другому профилю. Мы отметили конфликт, его разберёт поддержка.",
  candidate_already_linked: "К вашему профилю уже привязан другой участник ФСП.",
  fsp_ambiguous: "По этому email нашлось несколько участников. Укажите ID участника.",
  code_expired: "Код истёк или не запрашивался. Запросите новый.",
  too_many_attempts: "Слишком много неверных попыток. Запросите новый код.",
  invalid_code: "Код не подошёл. Проверьте и попробуйте ещё раз.",
  fsp_auth_error: "ФСП не подтвердила вход. Попробуйте ещё раз.",
  fsp_unavailable: "Интеграция с ФСП сейчас недоступна. Попробуйте позже.",
  consent_required: "Нужно согласие на обработку персональных данных.",
  sync_too_often: "Обновлять можно не чаще раза в 10 минут.",
  fsp_not_linked: "Сначала привяжите профиль ФСП.",
  state_invalid: "Сессия входа через ФСП устарела. Начните заново.",
  denied: "Вы отказались от доступа в ФСП.",
  unauthorized: "Войдите заново и повторите.",
};

export function fspErrorText(code: string | null | undefined): string {
  return (code && MESSAGES[code]) || "Не получилось связаться с ФСП. Попробуйте ещё раз.";
}

export function fspApiError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 429 && !e.code) return MESSAGES.sync_too_often;
    return fspErrorText(e.code);
  }
  return fspErrorText(null);
}
