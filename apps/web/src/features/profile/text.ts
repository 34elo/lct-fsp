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
  github: "GitHub",
  test: "Тест",
  ai_interview: "ИИ-интервью",
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

export function points(n: number): string {
  const v = Math.round(n * 10) / 10;
  return `${v > 0 ? "+" : ""}${v}`.replace(".", ",");
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
  seenAs: "Так вас видят компании, пока вы не примете оффер",
  noGrade: "Категория и грейд появятся, когда в профиле будут навыки: загрузите резюме или подключите ФСП.",
  preliminary: "Предварительно: пока мало подтверждённых фактов",
  strengthTitle: "Что усилит профиль",
  strengthHint: "Чем больше проверяемого, тем выше доверие к навыкам и точнее грейд.",
  strengthDone: "есть",
  strengthTodo: "добавить",
  editLink: "Заполнить профиль вручную",
  pdf: "Скачать PDF",
  pdfBusy: "Готовим PDF…",
  pdfError: "Не удалось скачать PDF. Попробуйте ещё раз.",
  graph: "Граф доказательств",
  claimedTitle: "Заявлено и подтверждено",
  claimedHint: "Что вы указали в опросе или резюме и что подтвердил тест.",
  skillsEmpty: "Пока нет навыков. Загрузите резюме или подключите ФСП, и они появятся здесь.",
  skillsHint: "Нажмите на навык, чтобы увидеть, чем он подтверждён. Пунктир: заявлено или выведено, без доказательств сила не растёт.",
  fspEmpty: "Результатов ФСП пока нет. Привяжите профиль ФСП: соревнования и разряды появятся здесь и усилят грейд.",
  fspImported: "Данные ФСП загружены, навыки и грейд обновлены.",
} as const;

export const STRENGTH_ITEMS = [
  { key: "resume", label: "Резюме", hint: "навыки с цитатами из текста", to: "/onboarding" },
  { key: "fsp", label: "ФСП", hint: "результаты и разряды соревнований", to: "/me/settings" },
  { key: "github", label: "GitHub", hint: "код станет доказательством", to: "/onboarding" },
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
  contactsHint: "Видны только вам. Работодатель получит их после того, как вы примете оффер.",
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
  interests: "Вами интересуются",
  strength: "Сила",
  place: "Место",
  interestsTile: "Интересы",
  top: (p: number) => `топ-${p} %`,
  none: "—",
  rating: (v: string) => `${v} / 5`,
} as const;

/** Источник подтверждения навыка — метка в строке «Навыки» на Главной. */
export const SOURCE_TAG: Record<string, string> = { test: "тест", fsp: "ФСП", github: "GitHub", resume: "резюме", task: "задание" };

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
  viewsHint: "за 30 дней",
  peers: "Где ты среди своих",
  peersSize: (n: number) => `${n} чел.`,
  peersLabel: (category: string) => `Точечная диаграмма категории ${category}`,
  you: "ты",
  yLabel: "ожидания, ₽",
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
