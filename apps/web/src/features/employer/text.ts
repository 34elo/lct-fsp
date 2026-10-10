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
  anon: "Карточки анонимны: имя, контакты и компании открываются после принятия приглашения.",
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

export const COMPANY_STATUS_LABEL: Record<string, string> = {
  pending: "На модерации",
  verified: "Проверена",
  rejected: "Отклонена",
  blocked: "Заблокирована",
};

export const COMPANY_STATUS_HINT: Record<string, string> = {
  pending: "Публиковать вакансии и отправлять приглашения можно после проверки компании администратором ФСП.",
  verified: "Компания проверена: можно публиковать вакансии и отправлять приглашения.",
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
  offer: "Приглашение",
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

/** Подбор `/employer` (E38-8, макеты `v2_employer__first_*`, `v2_employer__results_*`). Работодателю — «вы». */
export const MATCH_TEXT = {
  title: "Подбор",
  queryLabel: "Кого вы ищете",
  placeholder: "Кого вы ищете: роль, грейд, навыки, вилка",
  submit: "Подобрать",
  notUnderstood: "Не поняли запрос. Назовите роль или навыки: «Backend на Python, Middle».",
  failed: "Не удалось подобрать. Попробуйте ещё раз.",
  understood: "Поняли так",
  categories: "Ваши категории",
  categoriesLoadFailed: "Не удалось загрузить категории",
  people: (n: number) => `${n} ${plural(n, "человек", "человека", "человек")}`,
  peopleShort: "чел",
  fsp: "ФСП",
  affinity: (p: number) => `Совпадение с запросом ${p} %`,
  best: "Лучшие совпадения",
  top3: "топ-3",
  more: (n: number) => `Ещё ${n}`,
  byMatch: "по совпадению",
  colMatch: "совп.",
  colCandidate: "кандидат",
  colGrade: "грейд",
  colSkills: "навыки",
  colSalary: "ожидания, тыс. ₽",
  open: "Открыть профиль",
  candidatesFailed: "Не удалось загрузить кандидатов",
  retry: "Повторить",
  nothing: "Под запрос никого нет",
  nothingHint: "Опишите навыки другими словами или уберите ограничения по формату и бюджету.",
  nobodyNear: "В ближайших категориях пока никого нет",
  nobodyNearHint: "Подпишитесь на категорию — новые люди придут в ленту.",
  examples: "Например",
  exampleList: [
    "Backend на Python, Middle, до 220 тыс., удалёнка",
    "Frontend на React, Junior, офис в Москве",
    "Data-аналитик, SQL и Python, Middle",
  ],
  subscriptions: "Подписки",
  manageSubscriptions: "Подписки на категории",
  anyGrade: "любой грейд",
  anyTerms: "любые условия",
  onlyConfirmed: "подтверждён",
  anyConfirmed: "заявлен",
  upTo: (s: string) => `до ${s}`,
  feed: "Лента",
  today: "сегодня",
  feedEmpty: "Событий пока нет",
  feedEmptyHint: "Здесь появятся интересы, приглашения и новые кандидаты по вашим подпискам.",
  subscriptionsEmpty: "Подписок пока нет",
  subscriptionsEmptyHint: "Подпишитесь на категорию, и новые люди придут в ленту.",
  subscribe: "Подписаться на категорию",
  describeNeed: "Описать потребность",
  noCompany: "Сначала расскажите о компании",
  noCompanyHint: "Подбор открывается после регистрации компании: так кандидаты видят, кто им пишет.",
  noCompanyAction: "Начать настройку",
  feedNoCompanyHint: "Лента заработает, когда вы зарегистрируете компанию.",
  registerCompany: "Зарегистрировать компанию",
  feedFailed: "Лента не загрузилась",
  confirmedCount: (n: number) => `${n} ${plural(n, "навык подтверждён", "навыка подтверждены", "навыков подтверждены")}`,
  from: (s: string) => `от ${s}`,
  noGrade: "без грейда",
} as const;

/** Поиск сотрудников на «Подборе» (E39-21): строка с тегами, фильтры, категории с объяснением, компактная подборка. */
export const FIND_TEXT = {
  queryLabel: "Кого вы ищете",
  queryPlaceholder: "Навык или профессия: Python, Backend… или фраза целиком",
  queryHint: "Выберите навык или профессию из подсказок. Фразу целиком — Enter, разберём её в условия.",
  queryEmpty: "Начните вводить навык или профессию",
  parseOption: (q: string) => `Разобрать «${q}» в условия`,
  parsing: "Разбираем запрос…",
  hintSkill: "навык",
  hintProfession: "профессия",
  hintNew: "новый навык",
  notRecognized: (words: string) => `Не распознали: ${words}. Выберите навык из подсказок.`,
  nothingRecognized: "Не нашли в фразе навыков и условий. Выберите навык или профессию из подсказок.",
  parseFailed: "Не удалось разобрать запрос. Выберите навык из подсказок.",
  needSubject: "Добавьте навык или профессию — фильтры только сужают выдачу.",
  filters: "Фильтры",
  filtersCount: (n: number) => (n ? `Фильтры · ${n}` : "Фильтры"),
  reset: "Сбросить",
  resetAll: "Сбросить всё",
  active: "Условия",
  profession: "Профессия",
  professionAny: "Любая профессия",
  skills: "Навыки",
  skillsAdd: "Добавить навык",
  skillsPlaceholder: "Навык: Python, SQL…",
  viewLabel: "Режим подбора",
  viewCategories: "Категории",
  viewCandidates: "Кандидаты",
  shortlist: "В шорт-лист",
  shortlisted: "В шорт-листе",
  shortlistFailed: "Не удалось обновить шорт-лист. Попробуйте ещё раз.",
  shortlistNeedQuery: "Добавьте навык или профессию, чтобы собрать шорт-лист.",
  candidatesEmpty: "Под запрос никого нет",
  candidatesEmptyHint: "Ослабьте фильтры или уберите часть навыков.",
  candidatesFailed: "Не удалось загрузить кандидатов.",
  moreCandidates: "Показать ещё",
  grade: "Грейд",
  gradeHint: "Несколько грейдов — сплошным диапазоном.",
  trust: "Доверие к навыкам",
  trustAny: "Любое",
  trustHint: "Хотя бы один навык запроса подтверждён не ниже выбранного уровня.",
  confirmed: "Только подтверждённый грейд",
  confirmedHint: "Без пометок «нужно подтвердить» и «мало данных».",
  fsp: "ФСП",
  fspOnly: "Есть результаты ФСП",
  region: "Регион",
  regionPlaceholder: "Город",
  relocation: "Готов к переезду",
  salary: "Ожидания, ₽/мес",
  salaryFrom: "От",
  salaryTo: "До",
  format: "Формат работы",
  categories: "Категории",
  categoriesCount: (n: number) => `${n} ${plural(n, "категория", "категории", "категорий")}`,
  emptyCats: (n: number) => `Ещё ${n} без кандидатов`,
  hideEmpty: "Скрыть пустые",
  why: "Почему эти категории",
  whyLead: "Сравниваем навыки запроса с навыками профессий и берём профессии, где совпадение не ниже 40 %.",
  whyNamed: "выбрана в запросе",
  whySkills: (skills: string) => `совпадают навыки: ${skills}`,
  whyNoSkills: "навыков запроса у профессии нет",
  whyMatch: (p: number) => `совпадение ${p} %`,
  whyGrades: (g: string) => `Грейды — из запроса: ${g}.`,
  whyAllGrades: "Грейд в запросе не указан — показываем все три.",
  candidates: "Кандидаты",
  allInCategory: (n: number) => `Все ${n} в категории`,
  open: "Открыть",
  noCandidates: "В категории под эти фильтры никого нет",
  noCandidatesHint: "Ослабьте фильтры слева или выберите соседнюю категорию.",
  noCategories: "Под запрос нет категорий",
  noCategoriesHint: "Уберите часть навыков или выберите профессию в фильтрах.",
  failed: "Не удалось подобрать. Попробуйте ещё раз.",
  examplesLead: "Например — нажмите, и запрос разберётся в условия",
} as const;

/** Хвост строки ленты после псевдонима (`GET /employer/activity`, ActivityKind). */
export const FEED_TEXT: Record<string, (detail: string | null) => string> = {
  subscription_hit: (d) => (d ? `подошёл по подписке ${d}` : "подошёл по подписке"),
  interest_opened: () => "открыл ваш интерес",
  interest_declined: () => "отклонил ваш интерес",
  invitation_accepted: () => "принял приглашение",
  invitation_declined: () => "отклонил приглашение",
  task_answered: (d) => (d ? `ответил на задание «${d}»` : "ответил на задание"),
};

/** Общий шорт-лист работодателя `/employer/shortlist` (E38-12, бриф §6.12). */
export const SHORTLIST_PAGE_TEXT = {
  title: "Шорт-лист",
  list: "Отмеченные кандидаты",
  invite: "Пригласить",
  interest: "Интерес",
  open: "Открыть",
  empty: "Шорт-лист пуст",
  toMatch: "Перейти к подбору",
  failed: "Не загрузилось",
  code: (status: number) => `ошибка ${status}`,
  colCandidate: "кандидат",
  colGrade: "грейд",
  colSkills: "навыки",
  colSalary: "вилка",
  colInterest: "интерес",
  noInterest: "интерес не отправлен",
  waiting: "ожидает ответа",
  opened: "кандидат открыл интерес",
  lead: "Здесь кандидаты, которых вы отметили в подборе. Сравните их рядом и пригласите. Кандидат об отметке не узнаёт.",
  emptyHint: "Сохраняйте кандидатов из категорий, чтобы сравнить и пригласить.",
  remove: "Убрать",
  removeFailed: "Не удалось убрать кандидата. Попробуйте ещё раз.",
  pick: (name: string) => `Выбрать ${name} для сравнения`,
  compare: (n: number) => `Сравнить (${n})`,
  compareHint: "Отметьте от двух до четырёх кандидатов, чтобы сравнить их рядом.",
  compareMax: "Для сравнения можно выбрать не больше четырёх кандидатов.",
  compareTitle: "Сравнение кандидатов",
  compareClose: "Закрыть сравнение",
  compareTable: "Сравнение кандидатов рядом",
  rows: {
    grade: "Грейд",
    proof: "Подтверждение",
    skills: "Навыки",
    salary: "Вилка от",
    format: "Формат",
    city: "Город",
    fsp: "ФСП",
    interest: "Интерес",
  },
  confirmed: "грейд подтверждён тестом",
  claimed: "заявлен, не подтверждён",
  noFsp: "нет результатов",
  fspBest: (title: string, place: number, year: number) => `${title}: ${place} место, ${year}`,
  fspMore: (n: number) => `и ещё ${n}`,
} as const;

/** Онбординг новой компании (E39-7): данные компании → первый запрос → как устроен подбор. */
export const ONBOARDING_TEXT = {
  title: "Добро пожаловать в ФСП Карьеру",
  stepsLabel: "Шаги настройки",
  steps: ["Компания", "Кого ищете", "Как это работает"] as const,
  skip: "Пропустить",
  skipAll: "Пропустить настройку",
  next: "Дальше",
  company: {
    title: "Расскажите о компании",
    lead: "Название увидят кандидаты, когда вы напишете им. Остальное можно добавить позже.",
    name: "Название",
    nameError: "Укажите название компании: не короче двух символов.",
    site: "Сайт",
    sitePlaceholder: "https://",
    inn: "ИНН",
    innHint: "10 или 12 цифр. Нужен для проверки компании администратором ФСП.",
    innError: "ИНН состоит из 10 или 12 цифр.",
    submit: "Сохранить и продолжить",
    busy: "Сохраняем…",
    failed: "Не удалось сохранить компанию. Попробуйте ещё раз.",
  },
  need: {
    title: "Кого вы ищете",
    lead: "Опишите одной строкой: роль, грейд, навыки, вилка. Мы покажем подходящие категории.",
    skip: "Описать позже",
  },
  how: {
    title: "Как устроен подбор",
    lead: "Три шага от запроса до разговора с кандидатом.",
    cards: [
      { key: "category", title: "1. Категория", text: "Вы описываете потребность, мы показываем категории «профессия × грейд» и лучших людей в каждой." },
      { key: "interest", title: "2. Интерес с вилкой", text: "Вы отмечаете интерес и сразу указываете вилку зарплаты. Контакты остаются закрытыми." },
      { key: "invitation", title: "3. Приглашение", text: "Кандидат принимает приглашение, и вы получаете сайт и Telegram для разговора." },
    ],
    done: "Перейти к подбору",
  },
} as const;

/** Страница компании и команда (E39-24): владелец правит, HR видит. */
export const COMPANY = {
  title: "Компания",
  loadError: "Не удалось загрузить компанию.",
  missing: "Компания ещё не зарегистрирована. Заполните данные: после проверки администратором ФСП откроются публикация вакансий и приглашения. Если вас пригласили в команду, откройте ссылку из письма.",
  status: "Статус",
  name: "Название",
  nameError: "Укажите название компании.",
  inn: "ИНН",
  site: "Сайт",
  about: "О компании",
  aboutHint: "Кандидаты видят описание в приглашении. Поддерживается Markdown: заголовки, списки, таблицы.",
  aboutEmpty: "Описание пока не заполнено.",
  save: "Сохранить",
  register: "Зарегистрировать компанию",
  saved: "Сохранено.",
  readonly: "Данные компании меняет владелец. Вам доступны подбор, шорт-лист и приглашения.",
  tasks: "Тестовые задания компании",
  team: "Команда",
  teamHint: "Владелец правит компанию и приглашает HR. HR ведут подбор, шорт-лист и приглашения.",
  roles: { admin: "Владелец", member: "HR" } as Record<string, string>,
  you: "вы",
  noName: "Имя не указано",
  remove: "Убрать",
  removeConfirm: (who: string) => `Убрать ${who} из команды? Доступ к компании пропадёт сразу.`,
  inviteTitle: "Пригласить HR",
  inviteEmail: "Email сотрудника",
  inviteSubmit: "Пригласить",
  inviteHint: "Отправим письмо со ссылкой. Ссылка действует 7 дней; принять её можно аккаунтом работодателя с этим email.",
  inviteCreated: "Приглашение создано. Если письмо не дошло, отправьте ссылку сами:",
  copy: "Скопировать ссылку",
  copied: "Скопировано",
  pending: "Ждут ответа",
  until: (d: string) => `до ${d}`,
  revoke: "Отозвать",
  teamError: "Не удалось загрузить команду.",
  actionError: (code?: string) =>
    code === "already_member"
      ? "Этот человек уже в команде."
      : code === "rate_limited"
        ? "Слишком много приглашений, попробуйте позже."
        : code === "owner_cannot_be_removed"
          ? "Владельца нельзя убрать из компании."
          : "Не удалось выполнить действие. Попробуйте ещё раз.",
  profileLink: "Ваше имя, должность и фото — в настройках профиля",
} as const;

/** Приглашение в команду по ссылке `/invite/company/:token` (E39-24). */
export const INVITE = {
  title: "Приглашение в команду",
  lead: (company: string, who: string | null) => (who ? `${who} приглашает вас в команду компании «${company}».` : `Вас приглашают в команду компании «${company}».`),
  role: "Роль — HR: подбор, шорт-лист и приглашения кандидатам. Данные компании меняет владелец.",
  forEmail: (email: string) => `Приглашение отправлено на ${email}. Войдите или зарегистрируйтесь как работодатель с этим email.`,
  login: "Войти",
  register: "Зарегистрироваться",
  accept: "Принять приглашение",
  notEmployer: "Принять приглашение можно только аккаунтом работодателя. Выйдите и войдите с email из приглашения.",
  invalid: "Приглашение не найдено",
  invalidHint: "Ссылка неверна, отозвана, уже использована или истекла. Попросите владельца компании прислать новую.",
  toHome: "На главную",
  error: (code?: string) =>
    code === "invite_email_mismatch"
      ? "Приглашение отправлено на другой email. Войдите аккаунтом с адресом из письма."
      : code === "already_member"
        ? "Вы уже состоите в другой компании."
        : code === "invite_not_found"
          ? "Приглашение больше не действует."
          : "Не удалось принять приглашение. Попробуйте ещё раз.",
} as const;
