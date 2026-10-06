import { ApiError } from "@/api/mutator";

export const GRADE: Record<string, string> = { junior: "Junior", middle: "Middle", senior: "Senior" };

export const GRADE_CARDS = [
  { grade: "junior", lead: "Уверенно пишу по ТЗ, задачи ставит наставник. Проверим основы языка, SQL, базовое мышление.", minutes: 20 },
  { grade: "middle", lead: "Веду фичу сам, вижу последствия решений. Добавим данные, архитектуру и разбор инцидентов.", minutes: 25 },
  { grade: "senior", lead: "Отвечаю за систему целиком. Упор на проектирование, оценку и цепочки-инциденты.", minutes: 30 },
] as const;

export const FORMAT_OPTIONS = [
  { value: "remote", label: "Удалёнка" },
  { value: "hybrid", label: "Гибрид" },
  { value: "office", label: "Офис" },
] as const;

export const KIND_LABEL: Record<string, string> = {
  exact: "вывод кода",
  estimate: "оценка на порядок",
  choice: "выбор",
  find_bug: "найди дефект",
  order: "порядок действий",
  sjt: "рабочая ситуация",
  chain: "цепочка-инцидент",
};

export const STEPS = ["Отрасль", "Профессия", "Стек", "Формат и вилка", "Грейд"] as const;

export const T = {
  // опрос (S1)
  surveyTitle: "Опрос и выбор грейда",
  surveyLead: "Опрос — это твои ожидания. Грейд на профиле станет подтверждённым только после теста.",
  prefilled: "Заполнили из резюме · проверь",
  stepOf: (n: number, total: number) => `Шаг ${n} из ${total}`,
  industry: "Отрасль",
  industryHint: "Например: электронная коммерция",
  profession: "Профессия",
  professionQ: "Кем ты хочешь работать?",
  stack: "Стек",
  stackQ: "Какой у тебя стек?",
  stackHint: "Убери лишнее и добавь недостающее. До 30 навыков.",
  stackAdd: "добавить навык",
  stackAddBtn: "Добавить",
  stackRemove: (s: string) => `Убрать ${s}`,
  formats: "Формат работы",
  salary: "Ожидания по зарплате, ₽/мес",
  salaryFrom: "От",
  salaryTo: "До",
  gradeQ: "На какой грейд претендуешь",
  gradeMinutes: (m: number) => `10–24 задания · около ${m} минут`,
  gradeHint:
    "Грейд на профиле будет «предварительно» (пунктир), пока ты не пройдёшь тест. Завысить можно, но тест остановится раньше: честнее выбирать то, что ты правда тянешь.",
  historyHint: "Каждое сохранение — новая запись, история остаётся в «Истории попыток».",
  next: "Дальше",
  back: "Назад",
  save: "Сохранить опрос",
  saved: "Опрос сохранён",
  saveAndStart: "Сохранить и начать тест",
  historyLink: "История попыток",
  invalidRange: "«От» не может быть больше «До».",
  needProfession: "Выберите профессию.",
  needGrade: "Выберите грейд, чтобы начать тест.",
  loading: "Загружаем…",
  // тест (S2)
  testTitle: "Тест",
  taskN: (n: number) => `Задание ${n}`,
  answered: (n: number) => `отвечено ${n}`,
  progressHint: "тест закончится сам, когда результат станет ясен",
  progressLabel: "Прогресс теста",
  dontKnow: "Не знаю",
  answer: "Ответить",
  sending: "Отправляем…",
  rules: "Правила теста",
  rulesList: [
    "По одному заданию, назад вернуться нельзя.",
    "Таймер у каждого задания свой, он не останавливается.",
    "Правильность ответов не показываем, чтобы задания оставались честными.",
    "Уход со вкладки учитываем, камеры нет.",
  ],
  declared: "Заявленный грейд",
  range: "От 10 до 24 заданий. Можно сделать паузу между заданиями: попытка сохранится на 24 часа.",
  noBack: "Назад нельзя · правильность не показываем",
  timeLeft: "Осталось времени",
  timeUp: "Время вышло, ответ отправлен.",
  exactLabel: "Ответ",
  exactHint: "Число или строка, как в выводе. Пробелы по краям не важны.",
  estimateLabel: "Оценка",
  estimateHint: "Нужен порядок величины, не точное число. Калькулятор не нужен.",
  findBugHint: (n: number) => `Выбрано строк: ${n}. Засчитывается доля найденных.`,
  orderHint: "Расставьте варианты в правильном порядке: от первого к последнему.",
  sjtHint: "Расставьте действия от самого эффективного к наименее эффективному.",
  moveUp: (s: string) => `Выше: ${s}`,
  moveDown: (s: string) => `Ниже: ${s}`,
  chainStep: (n: number, total: number) => `Шаг ${n} из ${total}`,
  chainNext: "Дальше по цепочке",
  chainLead: "Инцидент разворачивается по шагам. Вернуться к предыдущему шагу нельзя.",
  finishing: "Считаем результат…",
  // результат (S3)
  resultTitle: "Результат теста",
  confirmed: "подтверждён",
  notConfirmed: "не подтверждён",
  validUntil: (d: string) => `Действует 12 месяцев — до ${d}`,
  tasks: "заданий",
  confidence: "уверенность",
  confidenceHigh: "высокая",
  confidenceLow: "низкая",
  integrity: "честность",
  failedTitle: "В этот раз грейд не подтвердился",
  failedText: "Это не отметка о неудаче: профиль и прежний грейд остаются. Слабые навыки ведут в «Рост».",
  needsConfirmation: "Результат требует подтверждения: уверенность оценки низкая.",
  lowConfidence: "Банк заданий кончился раньше, чем результат стал однозначным. Решение принято с пометкой «низкая уверенность».",
  upgradeTitle: "Бонусный этап пройден",
  upgradeAvailable: (g: string) => `Тебе доступен ${g}`,
  upgradeText:
    "Ты отвечал на уровне следующего грейда. Повышение принимаешь ты сам: потом смена грейда — не раньше чем через 90 дней.",
  upgradeAccept: (g: string) => `Принять ${g}`,
  upgradeKeep: (g: string) => `Остаться на ${g}`,
  upgradeDone: "Повышение принято. Грейд обновлён в профиле.",
  upgradeKept: "Остаёмся на текущем грейде. Предложение можно принять, пока оно действует.",
  bySkill: "Разбор по навыкам",
  bySkillLead: "Показываем, где просело, а не какие ответы верные: задания остаются честными для всех. Слабые навыки ведут в «Рост».",
  explainTitle: "Объясни ответ",
  explainLead: "Задания, где набрано не всё. Правильные ответы не показываем, чтобы задания оставались честными: разберём, почему могло не получиться.",
  explainTask: (n: number) => `Задание ${n}`,
  explainMyReason: "Как вы сами это объясняете",
  explainMyReasonNone: "Не выбрано",
  explainAsk: "Объяснить",
  explainRetry: "Объяснить ещё раз",
  explainWhy: "Причина по правилам",
  explainMisconception: "Частое заблуждение",
  explainTruth: "На деле",
  explainMatch: "Ваше объяснение совпало с причиной по правилам.",
  explainDiffer: "Ваше объяснение отличается: проверьте и вариант из разбора.",
  explainSourceLlm: "Текст подготовила локальная модель; причина определена правилами.",
  explainSourceTemplate: "Шаблонное объяснение; причина определена правилами.",
  explainNotAnswered: "На это задание ответа не было.",
  explainLimit: "Слишком много запросов. Попробуйте позже.",
  selfReasons: {
    misread: "Не так понял условие",
    rushed: "Поторопился",
    calc_error: "Ошибся в вычислении",
    knowledge_gap: "Не знал тему",
    guess: "Угадывал",
    technical: "Помешал сбой или время",
  } as Record<string, string>,
  colSkill: "Навык",
  colItems: "Заданий",
  colShare: "Доля",
  colTrust: "Доверие",
  holds: "держится",
  improve: "подтянуть",
  nextChange: (d: string) => `Следующая смена грейда — с ${d}`,
  retryAt: (g: string, d: string) => `Повтор ${g} — с ${d}`,
  cooldownRules: "Смена грейда — не чаще раза в 90 дней. Повтор того же грейда после неудачи — через 30 дней. Грейд принудительно не понижается.",
  openProfile: "Открыть профиль",
  openGrowth: "Рост",
  toHistory: "История попыток",
  inProgress: "Тест ещё идёт",
  inProgressText: "Результат появится, когда тест завершится.",
  continueTest: "Продолжить тест",
  // история (S4)
  historyTitle: "История попыток",
  newAttempt: "Новая попытка",
  attemptsTab: "Попытки",
  surveysTab: "Опросы",
  colDate: "Дата",
  colProfession: "Профессия · заявлено",
  colResult: "Результат",
  colIntegrity: "Честность",
  breakdown: "Разбор",
  passed: "прошёл",
  failed: "не прошёл",
  lowConf: "низкая уверенность",
  active: "идёт",
  abandoned: "прервана",
  emptyAttempts: "Попыток пока нет",
  emptyAttemptsText: "Пройдите опрос и тест: результат появится здесь.",
  emptySurveys: "Опросов пока нет",
  colSalary: "Вилка",
  colStack: "Стек",
  cooldownTitle: "Кулдауны и пересдачи",
  changeAfter: (d: string) => `Сменить грейд · ${d}`,
  retryAfter: (g: string, d: string) => `Пересдать ${g} · ${d}`,
  availableNow: "Доступно сейчас",
  change90: "Смена грейда — не чаще раза в 90 дней.",
  retry30: "Повтор того же грейда после неудачи — через 30 дней. Грейд ниже можно пройти сразу.",
  cooldown90: "кулдаун 90 дней",
  cooldown30: "кулдаун 30 дней",
  noCooldowns: "Ограничений нет: можно начинать новую попытку.",
  until: (d: string) => `доступно с ${d}`,
  // ошибки
  retry: "Повторить",
  errorTitle: "Не удалось загрузить",
  notFoundTitle: "Попытка не найдена",
  notFoundText: "Возможно, ссылка устарела.",
  cooldown: (d: string) => `Пересдача пока недоступна: попытка откроется ${d}.`,
  cooldownNoDate: "Пересдача пока недоступна: действует кулдаун.",
  emailNotVerified: "Сначала подтвердите email.",
  verifyEmail: "Подтвердить email",
  consentRequired: "Для теста нужны согласия на обработку данных.",
  toConsents: "Открыть согласия",
  attemptActive: "У вас есть незавершённая попытка по этой профессии.",
  continueAttempt: "Продолжить попытку",
  noItems: "Для этой профессии и грейда пока нет заданий. Попробуйте позже.",
  attemptFinished: "Попытка уже завершена.",
  unknownProfession: "Такой профессии нет в справочнике.",
  noUpgrade: "Повышение недоступно.",
  upgradeStale: "Предложение устарело: грейд уже изменился.",
  generic: "Что-то пошло не так. Попробуйте ещё раз.",
};

/** Первая строка `detail` кулдауна — ISO-дата, дальше пояснение (assessment.md §10). */
export function cooldownDate(detail: unknown): string | null {
  if (typeof detail !== "string") return null;
  const first = detail.trim().split(/\s+/)[0] ?? "";
  const d = new Date(first);
  return Number.isNaN(d.getTime()) ? null : first;
}

export const dateShort = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }) : "—";

export interface ErrorView {
  text: string;
  /** Ссылка рядом с текстом. */
  link?: { to: string; label: string };
  code?: string;
}

/** Ошибка API → текст и действие. Машинные коды: cooldown, email_not_verified, consent_required, not_found… */
export function errorView(e: unknown): ErrorView {
  if (!(e instanceof ApiError)) return { text: T.generic };
  const body = (e.body ?? {}) as { detail?: unknown };
  switch (e.code) {
    case "cooldown": {
      const d = cooldownDate(body.detail);
      return { code: e.code, text: d ? T.cooldown(dateShort(d)) : T.cooldownNoDate, link: { to: "/me/assessment/history", label: T.toHistory } };
    }
    case "email_not_verified":
      return { code: e.code, text: T.emailNotVerified, link: { to: "/verify-email", label: T.verifyEmail } };
    case "consent_required":
      return { code: e.code, text: T.consentRequired, link: { to: "/consents", label: T.toConsents } };
    case "attempt_active": {
      const id = typeof body.detail === "string" ? body.detail.trim() : "";
      return {
        code: e.code,
        text: T.attemptActive,
        link: id ? { to: `/me/assessment/attempts/${id}`, label: T.continueAttempt } : undefined,
      };
    }
    case "no_items":
      return { code: e.code, text: T.noItems };
    case "attempt_finished":
      return { code: e.code, text: T.attemptFinished };
    case "unknown_profession":
      return { code: e.code, text: T.unknownProfession };
    case "no_upgrade_offer":
      return { code: e.code, text: T.noUpgrade };
    case "upgrade_stale":
      return { code: e.code, text: T.upgradeStale };
    case "not_found":
      return { code: e.code, text: T.notFoundTitle };
    case "not_answered":
      return { code: e.code, text: T.explainNotAnswered };
    default:
      if (e.status === 429) return { code: e.code, text: T.explainLimit };
      return { code: e.code, text: e.status === 404 ? T.notFoundTitle : T.generic };
  }
}
