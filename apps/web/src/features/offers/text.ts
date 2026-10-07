import { ApiError } from "@/api/mutator";

export const OFFER_STATUS_LABEL: Record<string, string> = {
  interest: "Интерес",
  interest_opened: "Интерес открыт",
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
  wrong_company: "Не та компания",
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

/** Понятный текст по машинному `code` Problem Details (api.md, приглашения). */
export function offerErrorText(err: unknown, fallback = "Не удалось выполнить действие. Попробуйте ещё раз."): string {
  if (!(err instanceof ApiError)) return fallback;
  switch (err.code) {
    case "salary_range_required":
      return "Укажите вилку зарплаты: приглашение без вилки отправить нельзя.";
    case "invalid_salary_range":
      return "Верхняя граница вилки не может быть меньше нижней.";
    case "offer_exists":
      return "Приглашение этому кандидату по этой вакансии уже отправлен.";
    case "idempotency_key_reused":
      return "Этот запрос уже использован для другого приглашения. Обновите страницу и повторите.";
    case "offer_limit_exceeded":
      return "Лимит приглашений на сутки исчерпан. Попробуйте позже.";
    case "candidate_offer_limit_exceeded":
      return "Этот кандидат уже получил много приглашений за сутки. Попробуйте позже.";
    case "company_not_verified":
      return "Компания ещё не прошла верификацию, отправка приглашений недоступна.";
    case "vacancy_not_published":
      return "Вакансия не опубликована. Опубликуйте её и повторите.";
    case "vacancy_not_found":
      return "Вакансия не найдена.";
    case "candidate_not_found":
      return "Кандидат не найден или скрыл анкету.";
    case "offer_expired":
      return "Срок приглашения истёк.";
    case "invalid_transition":
      return "Это действие уже недоступно: статус приглашения изменился.";
    case "offer_closed":
      return "Переписка по этому приглашению закрыта.";
    case "empty_message":
      return "Сообщение не может быть пустым.";
    case "contacts_not_revealed":
      return "Контакты откроются после принятия приглашения.";
    case "contacts_revoked":
      return "Кандидат отозвал доступ к контактам.";
    case "offer_not_found":
      return "Приглашение не найден.";
    case "interest_limit_exceeded":
      return "Недельный лимит интересов исчерпан. Попробуйте позже.";
    case "interest_not_found":
      return "Интерес не найден: он истёк или отозван.";
    case "interest_not_opened":
      return "Приглашение можно отправить после того, как кандидат откроет интерес.";
    case "title_required":
      return "Без вакансии укажите название приглашения.";
  }
  if (err.status === 429) return "Слишком много запросов. Подождите немного и повторите.";
  if (err.status === 409) return "Состояние приглашения изменилось. Обновите страницу.";
  if (err.status === 422) return "Проверьте заполнение формы.";
  return fallback;
}

/** Тексты экрана E5 (мои приглашения, канбан). */
export const BOARD_TEXT = {
  title: "Мои приглашения",
  subtitle: (n: number) => `Отправлено приглашений: ${n}. Колонки — статусы, в «Закрыто» отказы, истёкшие и отозванные.`,
  columns: { interest: "Интерес", sent: "Отправлен", viewed: "Просмотрен", interview: "Интервью", accepted: "Принят", hired: "Нанят", closed: "Закрыто" },
  tabs: "Статусы приглашений",
  count: (n: number) => `Карточек: ${n}`,
  emptyColumn: "Пока пусто",
  deleted: "Кандидат удалил анкету",
  reason: (r: string) => `Отклонён · ${r}`,
  replyBy: (d: string) => `ответ до ${d}`,
  yourTurn: "Ждёт вашего ответа",
  kpiViewed: "Просмотрено",
  kpiAccepted: "Приняли",
  kpiHired: "Нанято",
  loadError: "Не удалось загрузить приглашения",
  empty: "Приглашений пока нет",
  emptyHint: "Найдите кандидата в поиске и отправьте первое приглашение с вилкой.",
  toSearch: "Перейти к подбору",
  declinesTitle: "Почему отказываются",
  declinesTotal: (n: number) => `отказов: ${n}`,
  hintLabel: "Что подсказывает система",
  hintDefault: "Откройте вакансию и сверьте требования с тем, что ищут кандидаты.",
  hint: {
    wrong_stack: "Уточните обязательные навыки: если стек не жёсткий, переведите часть навыков в «желательные» и укажите смежные.",
    low_salary: "Нижняя граница вилки ниже ожиданий кандидатов. Живая подсказка в окне приглашения покажет это до отправки.",
    wrong_format: "Проверьте форматы работы в вакансии: удалённый или гибридный формат расширяет круг кандидатов.",
    wrong_grade: "Сверьте диапазон грейдов в вакансии с тем, кого вы приглашаете.",
    not_looking: "Кандидаты со статусом «не ищу» откликаются реже: ищите среди активных.",
  } as Record<string, string>,
  openVacancies: "Открыть вакансии",
};

/** Тексты экрана M2 (приглашения кандидата). */
export const CAND_TEXT = {
  title: "Приглашения",
  newCount: (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "новый" : "новых"}`,
  empty: "Приглашений пока нет",
  emptyHint: "Они приходят сюда и в Telegram, когда компании находят ваш профиль.",
  loadError: "Не удалось загрузить приглашения.",
  past: "Прошлые приглашения",
  pastSummary: (a: number, d: number, e: number) => `принято ${a} · отклонено ${d} · истёк ${e}`,
  invite: "Приглашение без вакансии",
  response: "Ваш отклик",
  back: "Все приглашения",
  notFound: "Приглашение не найден.",
  salaryLabel: "Вилка в месяц",
  fromCompany: "Сообщение компании",
  description: "О приглашении",
  contactVia: (m: string) => `Связь: ${m}`,
  why: "Почему вы подходите",
  accept: "Принять",
  decline: "Не подходит",
  ask: "Задать вопрос",
  sheetTitle: "Почему не подходит?",
  sheetHint: "Один тап. Компания увидит причину без имени и контактов.",
  cancel: "Отмена",
  accepted: "Приглашение принят",
  acceptedHint: "Компания получила ваши контакты и свяжется с вами. Пока можно общаться здесь.",
  next: "Что дальше",
  revoke: "Отозвать доступ к контактам",
  revokeTitle: "Отозвать доступ к контактам?",
  revokeHint: "Компания перестанет видеть ваши контакты. Переписка здесь останется, принятое приглашение не отменяется.",
  revokeConfirm: "Отозвать",
  revoked: (d: string) => `Вы отозвали доступ к контактам ${d}. Компания их больше не видит.`,
  yourDecline: (r: string) => `Ваш отказ: ${r}`,
  below: (from: string) => `Ниже ваших ожиданий (от ${from})`,
  belowPlain: "Ниже ваших ожиданий",
  replyBy: (d: string, n: number) => `${d} · осталось ${n} дн.`,
};

/** Тексты «Вами интересуются» (кандидат) и интереса/приглашения (работодатель), ADR-026. */
export const CONTACTS_REVOKED_TEXT = "Кандидат отозвал доступ к контактам. Связаться можно через переписку здесь.";

export const INT_TEXT = {
  title: "Вами интересуются",
  lead: "Компании отметили ваш профиль и показали вилку. Контакты остаются скрытыми, пока вы не примете приглашение.",
  count: (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "компания интересуется" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? "компании интересуются" : "компаний интересуются"} вами`,
  range: (r: string) => `Вилки компаний: ${r}`,
  empty: "Пока никто не интересуется",
  emptyHint: "Интересы появятся здесь и в Telegram, когда компании найдут ваш профиль. Подтверждённые навыки и тест повышают шанс.",
  loadError: "Не удалось загрузить интересы.",
  back: "Все приглашения",
  banner: (n: number) => `Вами интересуются: ${n}`,
  bannerHint: "Компании отметили ваш профиль и ждут, откроете ли вы интерес.",
  open: "Открыть интерес",
  notInterested: "Не интересно",
  opened: "Вы открыли интерес. Ждём приглашение от компании.",
  openedShort: "Открыто, ждём приглашение",
  until: (d: string, n: number) => `Действует до ${d} · осталось ${n} дн.`,
  fromCompany: "Сообщение компании",
  why: "Почему вы",
  whyNone: "Причины совпадения недоступны.",
  unconfirmed: "Что не подтверждено",
  reliability: "Как компания отвечает",
  responseRate: (p: number) => `отвечает на ${p}% обращений`,
  avgHours: (h: number) => `в среднем за ${h < 24 ? `${Math.max(1, Math.round(h))} ч` : `${Math.round(h / 24)} дн.`}`,
  noReliability: "Мало данных о скорости ответов",
  sheetTitle: "Почему не интересно?",
  sheetHint: "Один тап. Компания увидит причину без вашего имени.",
  cancel: "Отмена",
  declineReasons: ["low_salary", "wrong_format", "wrong_company", "not_looking"] as const,
  factor: { grade: "Грейд", skills: "Навыки", salary: "Вилка", format: "Формат" } as Record<string, string>,
};

export const EMP_INT_TEXT = {
  titleInterest: (name: string) => `Интерес к кандидату ${name}`,
  leadInterest: "Первый шаг без обязательств: кандидат увидит вилку и «почему вы». Контакты не раскрываются.",
  titleInvite: (name: string) => `Приглашение кандидату ${name}`,
  leadInvite: "Кандидат открыл интерес. Уточните вилку и отправьте приглашение: после принятия раскроются контакты.",
  infoInterest: "Интерес действует 7 дней. Кандидат получит его в кабинет и Telegram. Лимит интересов в неделю ограничен.",
  infoInvite: "Срок ответа на приглашение 7 дней.",
  sendInterest: "Отметить «интересен»",
  sendInvite: "Отправить приглашение",
  invite: "Пригласить",
  interestBtn: "Проявить интерес",
  messageInterest: "Короткое сообщение (до 300 символов)",
  suggest: (to: string, pct: number) => `Поднимите верх вилки до ${to}: ответ вероятнее (${pct}%).`,
  apply: "Применить",
  respHours: (h: number) => `Кандидаты категории отвечают в среднем за ${h < 24 ? `${Math.max(1, Math.round(h))} ч` : `${Math.round(h / 24)} дн.`}.`,
  interestSent: "Интерес отправлен",
  waitOpen: "Ждём, пока кандидат откроет интерес. Его вилку и «почему вы» он уже видит.",
  waitInvite: "Кандидат открыл интерес. Отправьте приглашение, чтобы продолжить.",
  withdrawInterest: "Отозвать интерес",
  interestedYou: "Вами интересовался",
};

export const CONTACT_LABEL: Record<string, string> = { platform: "через платформу", email: "email", phone: "телефон", telegram: "Telegram" };
