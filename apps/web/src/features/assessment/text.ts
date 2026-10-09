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

/** ADR-025 п.4: первый шаг — IT-направление (это и есть профессия), отрасль не спрашиваем. */
export const STEPS = ["IT-направление", "Стек", "Формат и вилка", "Грейд"] as const;

/** Русское множественное: 1 работодатель, 3 работодателя, 5 работодателей. */
export function plural(n: number, one: string, few: string, many: string): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b === 1) return one;
  return b >= 2 && b <= 4 ? few : many;
}

export const T = {
  // поток «направление и навыки → грейд и ожидания → тест» (S1, E39-6)
  surveyTitle: "Тест и грейд",
  flow: ["Направление и навыки", "Грейд и ожидания", "Тест"] as const,
  flowLabel: "Шаги до теста",
  step1Lead: "От направления зависят задания теста и категория, в которой вас найдут работодатели.",
  step1Later: "Направление и навыки можно поменять потом в профиле.",
  step2Lead: "Тест подтвердит грейд. Ожидания видят только компании, которые пришлют приглашение.",
  skills: "Навыки",
  skillsHint: "Начните вводить — подскажем по справочнику. До 30 навыков.",
  beta: "бета",
  betaHint: "банк заданий пополняется",
  toProfile: "В профиль",
  saveStep: "Сохранить",
  fromResume: "из резюме",
  direction: "Направление",
  format: "Формат",
  fork: "Вилка",
  gradeLabel: "Грейд",
  gradeHelp: "Пояснение",
  expressShort: "Экспресс",
  expressMinutes: "3–5 мин",
  declares: "Заявляешь",
  expectations: "Ожидания",
  salaryFromShort: "от",
  startTest: "Начать тест",
  startLower: (g: string) => `Пройти ${g} сейчас`,
  nextAttempt: (g: string) => `Следующая попытка ${g}`,
  prefilled: "Заполнили из резюме · проверь",
  stepOf: (n: number, total: number) => `Шаг ${n} из ${total}`,
  profession: "IT-направление",
  professionQ: "В каком IT-направлении ты работаешь?",
  professionHint: "Backend, Frontend, Data/ML… От направления зависят навыки в тесте и категория в выдаче.",
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
  minutesShort: (m: number) => `~${m} мин`,
  gradeHint:
    "Грейд на профиле будет «предварительно» (пунктир), пока ты не пройдёшь тест. Завысить можно, но тест остановится раньше: честнее выбирать то, что ты правда тянешь.",
  historyHint: "Каждое сохранение — новая запись в «Истории попыток».",
  // экспресс-режим для жюри (E32-4a, ADR-025 п.7)
  express: "Экспресс-режим · 3–5 минут",
  expressHint: "6–8 заданий вместо 10–24. Оценка грубее, грейд получит метку «экспресс»; обычный тест заменит его в любой момент.",
  expressBadge: "экспресс",
  rangeExpress: "Экспресс-режим: от 6 до 8 заданий, 3–5 минут. Грейд будет с меткой «экспресс».",
  expressResult: "Экспресс-оценка: грейд помечен «экспресс». Обычный тест уточнит и заменит его без кулдауна.",
  next: "Дальше",
  back: "Назад",
  save: "Сохранить, тест позже",
  saved: "Сохранено",
  savedLater: "Тест можно пройти позже — кнопка будет на главной.",
  toHome: "На главную",
  saveAndStart: "Сохранить и начать тест",
  historyLink: "История попыток",
  invalidRange: "«От» не может быть больше «До».",
  needProfession: "Выберите IT-направление.",
  needGrade: "Выберите грейд, чтобы начать тест.",
  loading: "Загружаем…",
  // тест (S2)
  testTitle: "Тест",
  noActiveTitle: "Активного теста нет",
  takeTest: "Пройти тест",
  helpLabel: "Пояснение",
  orderPick: "Нажмите на вариант, затем на место, куда его поставить. Стрелки сдвигают на одну позицию.",
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
  inviteTitle: "Бонусный этап пройден",
  inviteAvailable: (g: string) => `Приглашение на тест ${g}`,
  inviteText:
    "Ты отвечал на уровне следующего грейда. Грейд сам не повышается: пройди отдельный тест. Кулдаун смены грейда на него не действует, а неудача не меняет грейд и не закрывает повтор.",
  inviteUntil: (d: string) => `Приглашение действует до ${d}`,
  inviteStart: (g: string) => `Пройти тест ${g}`,
  inviteLater: "Позже",
  inviteLaterText: "Приглашение сохранится, пока действует. Вернуться к нему можно из «Истории попыток».",
  inviteOpen: "Открыть тест по приглашению",
  inviteExpired: "Срок приглашения истёк.",
  invitedAttempt: "Тест по приглашению после бонусного этапа: неудача не меняет грейд и не закрывает повтор.",
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
  openProfile: "На главную",
  // результат v2 (E38-5): макеты v2_me-assessment-result__*
  confirmedTitle: (cat: string) => `${cat} — подтверждён`,
  notConfirmedTitle: (g: string) => `${g} не подтверждён`,
  howItWorks: "Как устроен тест",
  scaleTitle: "Шкала грейда",
  scaleAside: (v: number, g: string, cut: number) => `твой результат ${v} · порог ${g} ${cut}`,
  scaleAsideShort: (v: number, cut: number) => `${v} · порог ${cut}`,
  scaleNoData: "Шкала появится, когда оценка уровня будет посчитана.",
  typesTitle: "Разбивка по типам",
  typesAside: (g: string) => `тик — порог ${g}`,
  typesAsideShort: "тик — порог",
  types: { fundamental: "Фундамент", hard: "Хард", thinking: "Мышление", business: "Бизнес", soft: "Софт", experience: "Опыт" } as Record<string, string>,
  opened: "Что открылось",
  openedInterests: (n: number) => `${plural(n, "работодатель интересуется", "работодателя интересуются", "работодателей интересуются")} тобой`,
  openedCategory: (cat: string) => `Категория ${cat} открыта работодателям: они видят тебя в выдаче.`,
  claimedTitle: "Заявлено, не подтверждено",
  claimedSalary: "Ожидания от",
  topics: "Ответы по темам",
  growthLink: "Рост: подтянуть слабые навыки",
  errorsTitle: "Ошибки",
  noErrors: "Все задания засчитаны полностью.",
  toOffers: "Смотреть приглашения",
  passGrade: (g: string) => `Пройти ${g}`,
  lowerHint: (g: string) => `Можно пройти ${g} сейчас`,
  explainShort: "Объясни ответ",
  // разбор теста (E39-10)
  review: {
    link: "Разбор теста",
    title: "Разбор теста",
    lead: "Каждое задание: что спросили, ваш ответ, верный ответ и почему. Разбор виден только вам.",
    hide: "Скрыть объяснения",
    task: (n: number) => `Задание ${n}`,
    asked: "Что спросили",
    yours: "Ваш ответ",
    correct: "Верный ответ",
    noAnswer: "ответа не было",
    why: "Почему",
    collapse: "Свернуть объяснение",
    expand: "Показать объяснение",
    verdict: { ok: "Верно", part: "Частично", bad: "Неверно" } as Record<string, string>,
    group: (done: number, total: number) => `${done} из ${total} верно`,
    lines: "строки",
    step: (n: number) => `Шаг ${n}`,
    brushTitle: "Что подтянуть",
    brushLead: "Навыки, где набрано не всё. Начните с первых в списке.",
    brushNone: "Все задания засчитаны полностью, подтягивать нечего.",
    brushGo: "Открыть навигатор роста",
    empty: "В этой попытке нет заданий для разбора.",
    back: "К результату",
    activeTitle: "Тест ещё идёт",
    activeText: "Разбор откроется после завершения попытки.",
  },
  // баннер пути кандидата (E35-2a): одна фраза и одна кнопка
  banner: {
    survey: { text: "Выберите направление и пройдите тест — без него работодатели вас не найдут.", action: "Выбрать направление" },
    test: { text: "Направление выбрано. Осталось пройти тест — он подтвердит грейд.", action: "Пройти тест" },
    continue: { text: "Тест не закончен.", action: "Продолжить тест" },
  },
  openGrowth: "Рост",
  toHistory: "История попыток",
  inProgress: "Тест ещё идёт",
  inProgressText: "Результат появится, когда тест завершится.",
  continueTest: "Продолжить тест",
  // история (S4)
  historyTitle: "История попыток",
  newAttempt: "Новая попытка",
  attemptsTab: "Попытки",
  surveysTab: "Ожидания",
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
  emptyAttemptsText: "Выберите направление и пройдите тест: результат появится здесь.",
  emptySurveys: "Записей пока нет",
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
  expressDisabled: "Экспресс-режим сейчас выключен.",
  noInvite: "Приглашения по этой попытке нет.",
  inviteStale: "Приглашение неактуально: грейд уже не ниже.",
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
    case "express_disabled":
      return { code: e.code, text: T.expressDisabled };
    case "no_invite":
      return { code: e.code, text: T.noInvite };
    case "invite_expired":
      return { code: e.code, text: T.inviteExpired };
    case "invite_stale":
      return { code: e.code, text: T.inviteStale };
    case "not_found":
      return { code: e.code, text: T.notFoundTitle };
    case "not_answered":
      return { code: e.code, text: T.explainNotAnswered };
    default:
      if (e.status === 429) return { code: e.code, text: T.explainLimit };
      return { code: e.code, text: e.status === 404 ? T.notFoundTitle : T.generic };
  }
}
