import type { SearchStatus } from "@/api/model";

export const GRADE_LABEL: Record<string, string> = {
  intern: "Стажёр",
  junior: "Junior",
  junior_plus: "Junior+",
  middle: "Middle",
  middle_plus: "Middle+",
  senior: "Senior",
  lead: "Lead",
};

export const ROLE_LABEL: Record<string, string> = {
  backend: "Backend",
  frontend: "Frontend",
  fullstack: "Fullstack",
  mobile: "Mobile",
  ml: "ML",
  data_engineer: "Data",
  devops: "DevOps",
  qa: "QA",
  security: "Security",
  gamedev: "Gamedev",
  embedded: "Embedded",
  analyst: "Аналитик",
  product: "Product",
  designer: "Дизайн",
};

export const SOURCE_LABEL: Record<string, string> = {
  self: "Заявлено кандидатом",
  resume: "Резюме",
  test: "Тест",
  fsp: "ФСП",
  codeforces: "Codeforces",
};

export const SIGNAL_LABEL: Record<string, string> = {
  leadership: "Лидерство",
  teamwork: "Работа в команде",
  results: "Результаты",
  growth: "Рост",
};

export const STRENGTH_LABEL: Record<string, string> = {
  strong: "сильное подтверждение",
  present: "есть подтверждение",
};

export const STATUS_LABEL: Record<SearchStatus, string> = {
  active: "Активно ищу",
  open: "Открыт к предложениям",
  dnd: "Не беспокоить",
};

/** Уровень доверия 0..4 для точек (бэкенд отдаёт `level` как целое, но не гарантируем диапазон). */
export function dots(level: number): 0 | 1 | 2 | 3 | 4 {
  return Math.max(0, Math.min(4, Math.round(level))) as 0 | 1 | 2 | 3 | 4;
}

export function roleLabel(role: string): string {
  return ROLE_LABEL[role] ?? role;
}

export function dateRu(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

export const FSP_LEVEL_LABEL: Record<string, string> = {
  regional: "региональный уровень",
  interregional: "межрегиональный",
  national: "всероссийский",
  international: "международный",
};

export const DISCIPLINE_LABEL: Record<string, string> = {
  algorithmic: "Алгоритмическое программирование",
  product: "Продуктовое программирование",
  security: "Информационная безопасность",
  robotics: "Робототехника",
  uav: "Беспилотные системы",
};

export const RANK_LABEL: Record<string, string> = {
  rank_3: "3 разряд",
  rank_2: "2 разряд",
  rank_1: "1 разряд",
  cms: "Кандидат в мастера спорта",
  ms: "Мастер спорта",
};

export const TEAM_ROLE_LABEL: Record<string, string> = { captain: "капитан", member: "участник" };

/** «Июнь 2024 — н. в.» по ISO-датам `YYYY-MM...` из опыта. */
export function periodRu(start?: string | null, end?: string | null): string {
  const f = (v: string) => {
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
  };
  const a = start ? f(start) : "";
  const b = end ? f(end) : "по настоящее время";
  return a ? `${a} — ${b}` : "";
}

/** Тексты экрана профиля (макет D). */
export const T = {
  title: "Мой профиль",
  loading: "Загрузка профиля…",
  loadError: "Не удалось загрузить профиль",
  loadErrorHint: "Проверьте соединение и повторите.",
  seenAs: "Так вас видят компании, пока вы не примете приглашение",
  noGrade: "Категория и грейд появятся после теста.",
  preliminary: "Предварительно: пока мало подтверждённых фактов",
  strengthTitle: "Что усилит профиль",
  strengthHint: "Чем больше проверяемого, тем выше доверие к навыкам и точнее грейд.",
  strengthDone: "есть",
  strengthTodo: "добавить",
  editLink: "Заполнить профиль вручную",
  directionLink: "Направление и навыки",
  pdf: "Скачать PDF",
  pdfBusy: "Готовим PDF…",
  pdfError: "Не удалось скачать PDF. Попробуйте ещё раз.",
  graph: "Граф доказательств",
  claimedTitle: "Заявлено и подтверждено",
  claimedHint: "Что вы заявили перед тестом и что он подтвердил.",
  skillsEmpty: "Пока нет навыков. Выберите направление и пройдите тест или подключите ФСП, и они появятся здесь.",
  skillsHint: "Нажмите на навык, чтобы увидеть, чем он подтверждён. Пунктир: заявлено или выведено, без доказательств сила не растёт.",
  fspEmpty: "Результатов ФСП пока нет. Привяжите профиль ФСП: соревнования и разряды появятся здесь и усилят грейд.",
  fspImported: "Данные ФСП загружены, навыки и грейд обновлены.",
} as const;

export const STRENGTH_ITEMS = [
  { key: "resume", label: "Резюме", hint: "навыки с цитатами из текста", to: "/me/profile?tab=data" },
  { key: "fsp", label: "ФСП", hint: "результаты и разряды соревнований", to: "/me/profile?tab=data" },
  { key: "test", label: "Тест", hint: "подтверждает грейд", to: "/me/assessment" },
] as const;

export const CLAIM_STATUS_LABEL: Record<string, string> = {
  confirmed: "подтверждено",
  overclaimed: "тест ниже заявленного",
  underclaimed: "тест выше заявленного",
  unconfirmed: "тест не пройден",
};

/** Группы навыков (data/taxonomy/skills.yaml); порядок = порядок показа. */
export const GROUP_LABEL: Record<string, string> = {
  language: "Языки",
  backend: "Backend",
  frontend: "Frontend",
  storage: "Хранение данных",
  data_ml: "Данные и ML",
  devops: "DevOps",
  fundamentals: "Основы и алгоритмы",
  testing: "Тестирование",
  security: "Безопасность",
  mobile: "Mobile",
  embedded: "Embedded",
  gamedev: "Gamedev",
  product: "Продукт",
  design: "Дизайн",
  analysis: "Аналитика",
};

/** Ручная форма профиля `/me/profile/edit` (E20-7a). */
export const editText = {
  title: "Профиль вручную",
  lead: "Заявленное вами попадает в профиль как «заявлено»: сила доказательства небольшая, пока навык не подтверждён тестом, кодом или ФСП.",
  back: "К профилю",
  loadError: "Не удалось загрузить профиль",
  contactsTitle: "Контакты",
  contactsHint: "Видны только вам. Работодатель получит их после того, как вы примете приглашение.",
  email: "Почта",
  phone: "Телефон",
  telegram: "Telegram",
  stackTitle: "Стек",
  stackHint: "Технологии, с которыми вы работали. Список сохраняется целиком: убранное выключается.",
  stackSearch: "Найти технологию",
  stackNone: "Пока пусто",
  stackYears: "лет",
  stackRemove: "Убрать",
  expTitle: "Стаж",
  expYears: "Полных лет",
  expMonths: "Месяцев",
  rolesTitle: "Желаемые роли",
  rolesHint: "До 5 ролей.",
  softTitle: "Личные качества",
  softHint: "Только заявлено: без командных фактов на грейд не влияет.",
  ageTitle: "Возраст",
  ageHint: "Дату рождения не спрашиваем. Работодатель возраст не видит.",
  ageMinor: "Мне 15–17 лет",
  ageParent: "Родитель или законный представитель согласен на обработку моих персональных данных",
  ageHidden: "Без согласия родителя профиль не показывается работодателям.",
  save: "Сохранить",
  saving: "Сохраняем…",
  saved: "Профиль сохранён. Навыки и грейд пересчитываются.",
  errorUnknownSkill: "Одного из навыков нет в справочнике. Уберите его и повторите.",
  errorConsent: "Для сохранения нужно согласие на обработку персональных данных.",
  errorFallback: "Не удалось сохранить профиль, попробуйте позже",
  invalidEmail: "Проверьте адрес почты",
  invalidTelegram: "Telegram: @имя из 5–32 символов",
  invalidPhone: "Телефон: от 7 цифр",
  invalidExp: "Стаж: целое число от 0 до 600 месяцев",
} as const;

/** Главная кандидата `/me` (E38-1, макеты v2_me__before / v2_me__after). */
export const HOME = {
  title: "Главная",
  loading: "Загрузка главной…",
  loadError: "Не удалось загрузить главную",
  loadErrorHint: "Проверь соединение и повтори.",
  beforeTitle: "Пройди тест — без него тебя не видят работодатели",
  beforeAction: { survey: "Пройти тест", test: "Пройти тест", continue: "Продолжить тест" },
  claimed: "заявлено",
  express: "экспресс · 3–5 мин",
  constellationEmpty: "Заявленные навыки без подтверждения",
  nextStep: "Следующий шаг",
  steps: {
    test: { done: "Тест пройден", todo: "Пройти тест" },
    fsp: { done: "ФСП привязан", todo: "Привязать ФСП" },
    interest: { todo: "Ответить на интерес" },
  },
  nextTest: (grade: string) => `Тест на ${grade}`,
  nextTestAction: (grade: string) => `Пройти тест на ${grade}`,
  allDone: "Смотреть приглашения",
  cooldown: (date: string) => `Следующая попытка — ${date}`,
  confirmed: (date: string, express: boolean) => `подтверждён ${date}${express ? " · экспресс" : ""}`,
  notConfirmed: "не подтверждён",
  expectations: "Ожидания",
  salaryFrom: (v: string) => `от ${v}`,
  skills: "Навыки",
  skillClaimed: "заявлен",
  fsp: "Достижения ФСП",
  fspPlace: (place: number) => `${place} место`,
  constellation: "Созвездие навыков",
  legend: { confirmed: "подтверждено", claimed: "заявлено", adjacent: "смежные" },
  interests: "Приглашения и интересы",
  allInvites: "Все приглашения →",
  allSkills: "Все навыки →",
  tasks: "Регулярные задания",
  tasksHint: "Задания компаний по вашей категории: на грейд не влияют, работодатель видит результат.",
  tasksAll: "Все задания →",
  strength: "Сила",
  place: "Место",
  interestsTile: "Интересы",
  top: (p: number) => `топ-${p} %`,
  topCap: (p: number) => `Топ-${p} %`,
  none: "—",
  rating: (v: string) => `${v} / 5`,
} as const;

/** Источник подтверждения навыка — метка в строке «Навыки» на Главной. */
export const SOURCE_TAG: Record<string, string> = { test: "тест", fsp: "ФСП", resume: "резюме", task: "задание" };

/** Формат работы в карточке профиля: «Удалёнка или гибрид». */
export const FORMAT_WORD: Record<string, string> = { remote: "удалёнка", hybrid: "гибрид", office: "офис" };

/** Статистика кандидата `/me/stats` (E38-2, макеты v2_me-stats__*). */
export const STATS = {
  title: "Статистика",
  link: "Статистика",
  linkViews: (n: number) => `смотрели: ${n} ›`,
  loading: "Загрузка статистики…",
  empty: "Статистики пока нет",
  emptyAction: "Пройти тест",
  loadError: "Не загрузилось",
  errorCode: (status: number) => `ошибка ${status}`,
  views: "Смотрели",
  relative: "От лидера категории",
  relativeValue: (v: number) => `${Math.round(v)} %`,
  relativeGap: (gap: number, top: number) => `до топ-${top} % не хватает ${Math.round(gap * 10) / 10} п. п.`,
  relativeLeader: "ты лидер категории",
  partsTitle: "Из чего складывается сила",
  viewsHint: "за 30 дней",
  peers: "Где ты среди своих",
  peersSize: (n: number) => `${n} чел.`,
  peersLabel: (category: string) => `Точечная диаграмма категории ${category}`,
  you: "ты",
  xAxis: "уровень в тесте →",
  yAxis: "↑ сила профиля",
  peersNote: (category: string) =>
    `Свои — кандидаты категории ${category}, которые прошли тест. По горизонтали — уровень в тесте, по вертикали — сила профиля; чем выше и правее точка, тем сильнее кандидат.`,
  catTitle: "Твоя категория в цифрах",
  catCandidates: "Кандидатов в категории",
  catForks: "Вилки в интересах",
  catForksHint: (n: number) => `медиана по ${n} ${plural(n, "интересу", "интересам", "интересам")} к категории`,
  catForksNone: "компании пока не отмечали интерес",
  catCompanies: "Компаний ищут категорию",
  catCompaniesHint: "с опубликованной вакансией",
  heatmap: "Просмотры профиля",
  heatmapLabel: (total: number) => `Просмотры профиля по дням: ${total} за 30 дней`,
  heatmapCaption: (n: number) => `${n} ${plural(n, "компания смотрела", "компании смотрели", "компаний смотрели")} за 30 дней`,
  seenAs: "Как тебя видят",
  fspConfirmed: "подтверждён ФСП",
  history: "История тестов",
  passed: "подтверждён",
  failed: "не подтверждён",
  mode: { express: "экспресс", full: "полный" } as Record<string, string>,
} as const;

/** Русское множественное число: 1 компания, 2 компании, 5 компаний. */
export function plural(n: number, one: string, few: string, many: string): string {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b === 1) return one;
  if (b >= 2 && b <= 4) return few;
  return many;
}

/** Профиль кандидата `/me/profile` (E38-6, макеты v2_me-profile__*). */
export const PROFILE = {
  title: "Профиль",
  addEvidence: "Добавить доказательство",
  tasks: "Регулярные задания",
  tabsLabel: "Разделы профиля",
  tabs: { overview: "Обзор", skills: "Навыки", data: "Данные", graph: "Граф" },
  loading: "Загрузка профиля…",
  loadError: "Не загрузилось",
  errorCode: (status: number) => `ошибка ${status}`,
  empty: "Доказательств пока нет",
  confirmed: "Подтверждено",
  claimed: "Заявлено",
  claimedAndConfirmed: "Заявлено и подтверждено",
  published: "профиль опубликован",
  hidden: "профиль скрыт от компаний",
  testTag: (date: string) => (date ? `тест ${date}` : "тест"),
  claimedInResume: "заявлено в резюме",
  claimedSelf: "заявлено",
  derived: "выведено",
  skillLink: (name: string) => `${name}: чем подтверждён`,
  fspTitle: "Достижения ФСП",
  fspLinked: "привязан",
  fspNotLinked: "не привязан",
  resume: "Резюме",
  city: "Город",
  salary: "Ожидания",
  salaryFrom: (v: string) => `от ${v}`,
  format: "Формат",
  experience: "Опыт",
  roles: "Роли",
  notSpecified: "не указан",
  experienceMonths: (m: number) => {
    const y = Math.floor(m / 12);
    const mo = m % 12;
    return [y ? `${y} ${plural(y, "год", "года", "лет")}` : "", mo || !y ? `${mo} мес.` : ""].filter(Boolean).join(" ");
  },
  graphTitle: "Граф доказательств",
  legendFact: "факт",
  legendClaimed: "заявлено",
  emptyAction: "Пройти тест",
  tiles: { confirmed: "Подтверждено навыков", claimed: "Заявлено навыков", fsp: "Достижений ФСП" },
} as const;

/** Вкладка «Навыки» профиля (E39-15): поиск, фильтры, скрытие, по умолчанию топ-15. */
export const SKILLS = {
  title: "Навыки",
  search: "Поиск навыка",
  searchPlaceholder: "Например, Python",
  type: "Тип навыка",
  typeAll: "Все типы",
  trust: "Доверие",
  trustAny: "Любое доверие",
  trustFrom: (n: number) => `не ниже ${"●".repeat(n)}${"○".repeat(4 - n)}`,
  state: "Статус навыка",
  states: { all: "Все", confirmed: "Подтверждено", claimed: "Заявлено" },
  showHidden: (n: number) => `Показать скрытые (${n})`,
  shown: (n: number, total: number) => `Показано ${n} из ${total}`,
  showAll: (n: number) => `Показать все (${n})`,
  showTop: "Только первые 15",
  nothing: "Ничего не нашлось",
  nothingHint: "Измените поиск или сбросьте фильтры.",
  reset: "Сбросить фильтры",
  hide: (name: string) => `Скрыть ${name} от компаний`,
  unhide: (name: string) => `Вернуть ${name} в профиль`,
  hideShort: "Скрыть",
  unhideShort: "Вернуть",
  hiddenTag: "скрыт от компаний",
  hideError: "Не удалось сохранить. Попробуйте ещё раз.",
  hideHint: "Скрытый навык компании не видят ни в карточке, ни в выдаче. На грейд он не влияет.",
} as const;

/** Вкладка «Данные» профиля (E39-15): ФИО, контакты, опыт, образование, ссылки, ФСП. */
export const DATA = {
  personal: "Личные данные",
  fullName: "ФИО",
  email: "Email",
  phone: "Телефон",
  telegram: "Telegram",
  city: "Город",
  notSet: "не указано",
  nameHidden: "Видно вам. Компания увидит после приглашения.",
  nameOpen: "Видно вам и компаниям: открыто в настройках приватности.",
  privacyLink: "Приватность",
  contactsNote: "Контакты компания получит, только когда вы примете приглашение.",
  experience: "Опыт",
  education: "Образование",
  links: "Ссылки",
  preferences: "Пожелания к работе",
  preferencesEdit: "Изменить пожелания и стек",
  noExperience: "Опыт пока не указан.",
  noEducation: "Образование пока не указано.",
  noLinks: "Ссылок пока нет.",
  fromResumeOnly: "Опыт и образование заполняются из резюме: нажмите «Заполнить из резюме».",
  edit: "Изменить данные",
  save: "Сохранить",
  saving: "Сохраняем…",
  cancel: "Отмена",
  saved: "Данные сохранены.",
  saveError: "Не удалось сохранить, попробуйте ещё раз.",
  fromResume: "Заполнить из резюме",
  fromResumeHint: "PDF или DOCX до 10 МБ. Разбор заполнит поля ниже, вы проверите и сохраните.",
  resumeFile: "Файл резюме",
  uploading: "Загружаем…",
  parsing: "Разбираем резюме…",
  draftTitle: "Черновик из резюме",
  draftHint: "Мы заполнили поля по резюме. Проверьте, поправьте и сохраните: до сохранения компании ничего не видят.",
  draftSkills: (n: number) => `В резюме найдено навыков: ${n}. После сохранения они появятся в профиле как заявленные.`,
  draftReview: "Проверить черновик",
  draftFailed: "Не удалось разобрать резюме. Попробуйте другой файл или заполните вручную.",
  position: "Должность",
  company: "Компания",
  start: "Начало (ГГГГ-ММ)",
  end: "Конец (ГГГГ-ММ, пусто — по сей день)",
  institution: "Учебное заведение",
  degree: "Степень",
  field: "Специальность",
  yearEnd: "Год окончания",
  addExperience: "Добавить место работы",
  addEducation: "Добавить учёбу",
  addLink: "Добавить ссылку",
  remove: "Убрать",
  link: (i: number) => `Ссылка ${i}`,
  invalidLink: "Ссылка должна начинаться с http:// или https://",
  invalidMonth: "Формат ГГГГ-ММ, например 2023-09",
  invalidYear: "Год из четырёх цифр",
  present: "по сей день",
} as const;

/** Настройки приватности кандидата (E36-4, ADR-027): что видно работодателю до приглашения. */
export const privacyText = {
  title: "Что видит работодатель",
  hint: "Контакты закрыты, пока вы не примете приглашение или не откликнетесь сами. Настройки применяются сразу.",
  saveError: "Не удалось сохранить настройку",
  items: [
    { key: "full_name", label: "Имя и фамилия", hint: "Без вашего согласия работодатель видит только псевдоним." },
    { key: "companies", label: "Опыт и компании", hint: "Названия компаний в карточке; сроки и навыки опыта видны всегда." },
    { key: "fsp", label: "Достижения ФСП", hint: "Результаты соревнований в карточке и в доверии к навыкам." },
    { key: "region", label: "Регион", hint: "Город в карточке и в выдаче." },
  ],
} as const;

/** Настройки кандидата `/settings` (E38-7, E39-8, макеты v2_me-settings__*). */
export const SETTINGS = {
  title: "Настройки",
  loading: "Загрузка настроек…",
  loadError: "Не загрузилось",
  errorCode: (status: number) => `ошибка ${status}`,
  empty: "Согласия не даны — профиль скрыт от компаний",
  emptyAction: "Дать согласие",
  consents: "Согласия",
  consentsHint: "Обязательные согласия отозвать нельзя. Остальные применяются сразу.",
  consentError: "Не удалось сохранить согласие",
  notifications: "Уведомления",
  telegram: "Telegram",
  telegramLinked: "привязан",
  telegramLink: "Привязать",
  telegramLinkError: "Не удалось получить ссылку на бота",
  appearance: "Оформление",
  appearanceHint: "Пока вы не выбрали, тема совпадает с системной.",
  themeLabel: "Тема",
  themeLight: "Светлая",
  themeDark: "Тёмная",
  tabsLabel: "Разделы настроек",
  tabs: {
    profile: "Профиль",
    privacy: "Приватность",
    notifications: "Уведомления",
    consents: "Согласия",
    appearance: "Оформление",
    security: "Безопасность",
  },
  profile: {
    title: "Профиль",
    account: "Аккаунт",
    roles: { candidate: "Кандидат", employer: "Работодатель", fsp_admin: "Администратор ФСП" } as Record<string, string>,
    fullName: "ФИО",
    fullNameHint: "Компании видят имя только если вы открыли его в «Приватности».",
    company: "Название компании",
    companyDescription: "Описание компании",
    companyMore: "Остальные данные компании",
    companyNone: "Компания ещё не создана — заполните данные на странице «Компания».",
    companyReadonly: "Название и описание меняет администратор компании.",
    // E39-24: личный профиль сотрудника компании и админа ФСП
    staffHint: "Имя, должность и фото видят кандидаты в подписи ваших приглашений.",
    position: "Должность",
    positionPlaceholder: "Например, HR-партнёр",
    about: "О себе",
    aboutHint: "Пара строк о том, кого и как вы ищете. Поддерживается Markdown.",
    photo: "Фото",
    photoHint: "PNG, JPEG или WebP до 2 МБ.",
    photoUpload: "Загрузить фото",
    photoReplace: "Заменить фото",
    photoRemove: "Убрать фото",
    photoError: (code?: string) =>
      code === "file_too_large" ? "Файл больше 2 МБ." : code === "unsupported_file_type" ? "Нужна картинка PNG, JPEG или WebP." : "Не удалось загрузить фото.",
    companyLine: "Компания",
    companyRoles: { admin: "Владелец", member: "HR" } as Record<string, string>,
    companyOpen: "Открыть страницу компании",
    save: "Сохранить",
    saved: "Сохранено",
    saveError: "Не удалось сохранить",
    nameTooLong: "Не длиннее 120 символов",
    nameTooShort: "Не короче 2 символов",
  },
  security: {
    title: "Пароль",
    hint: "После смены пароля остальные устройства выйдут из аккаунта.",
    current: "Текущий пароль",
    next: "Новый пароль",
    repeat: "Повторите новый пароль",
    min: "Не короче 8 символов",
    mismatch: "Пароли не совпадают",
    same: "Новый пароль совпадает с текущим",
    submit: "Сменить пароль",
    done: "Пароль изменён",
    wrong: "Текущий пароль указан неверно",
    limit: "Слишком много попыток, попробуйте через час",
    error: "Не удалось сменить пароль",
    noPassword: "Вы вошли через Telegram, пароля у аккаунта нет.",
  },
} as const;
