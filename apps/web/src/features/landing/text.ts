/** Тексты лендинга v3 (docs/design/v3/landing/landing.html). Компании и цифры в примерах вымышленные. */
export const T = {
  brand: "ФСП Карьера",
  navAria: "Разделы",
  nav: [
    { id: "how", label: "Как это работает" },
    { id: "trust", label: "Доверие" },
    { id: "fsp", label: "ФСП" },
  ],
  themeToDark: "Тёмная тема",
  themeToLight: "Светлая тема",
  login: "Войти",
  ctaCandidate: "Пройти тест",
  ctaEmployer: "Ищу сотрудников",

  eyebrow: "Платформа Федерации спортивного программирования",
  heroTitle: "Тест вместо резюме. ",
  heroTitleEm: "Компании приходят сами",
  heroLead: "Десять минут, подтверждённая категория и приглашения с вилкой.",
  inviteWord: "приглашение",
  inviteNew: "Новое приглашение",
  offerCompany: "Северный код",
  offerMeta: "4.6 / 5 · проверена",
  offerSalary: "220–260 тыс. ₽",
  offerBasis: "до НДФЛ",
  offerGrade: "Backend · Middle · подтверждено",
  offerSkills: [
    { name: "Python", level: 3 },
    { name: "SQL", level: 2 },
    { name: "Docker", level: 2 },
  ],
  offerNote: "Ищем Backend на Python, удалённо. Ответ до 14.10.",
  secondCompany: "Кедр Софт",
  secondSalary: "180–230 тыс. ₽",
  matchTitle: "Совпадение",
  matchWho: "Backend #4821",
  matchAria: "Совпадение 92",

  howLabel: "Как это работает",
  howTitle: "Три шага для каждой стороны",
  tabsAria: "Сценарий",
  tabCandidate: "Кандидату",
  tabCompany: "Компании",
  candidateSteps: [
    { title: "Выбери направление", text: "Backend, Frontend, AI Engineer и другие.", icon: "target" },
    { title: "Пройди тест", text: "Около 10 минут, задания только твои.", icon: "test" },
    { title: "Получай приглашения", text: "Компании пишут сами, вилка видна сразу.", icon: "mail" },
  ],
  companySteps: [
    { title: "Опишите, кого ищете", text: "Одной фразой: стек, грейд, вилка.", icon: "search" },
    { title: "Выберите категорию", text: "Проверенные кандидаты по силе профиля.", icon: "grid" },
    { title: "Пригласите с вилкой", text: "Контакты открываются после согласия.", icon: "send" },
  ],

  trustLabel: "Почему этому можно верить",
  trustTitle: "Четыре отличия, которые видно сразу",
  variantTitle: "У каждого свой вариант теста",
  variantText: "Задания генерируются, списать не у кого.",
  variantMine: "твой вариант",
  variantOther: "другой кандидат",
  stopTitle: "Тест останавливается, когда уверен",
  stopText: "Не 60 вопросов, а столько, сколько нужно.",
  stopTask: "задание 11 из 60",
  stopConfidence: "уверенность 92 %",
  hintTitle: "Ошибка — это подсказка",
  hintText: "Разбор показывает, что подтянуть, а не штрафует.",
  hintSkill: "SQL",
  hintMistake: "путаешь LEFT и INNER JOIN",
  hintLearn: "подтянуть",
  hintTopic: "типы JOIN",
  forkTitle: "Вилка видна сразу",
  forkText: "Условия известны до разговора. Спама нет.",
  forkRange: "150–220 тыс. ₽",
  forkBasis: "до НДФЛ",
  forkNote: "вилка видна до первого сообщения",

  fspLabel: "ФСП",
  fspTitle: "Результаты соревнований ФСП поднимают тебя внутри категории",
  fspLead: "Привяжи аккаунт ФСП — достижения станут доказательством.",
  fspBadge: "достижение",
  fspAchievement: "Финалист Всероссийского финала по продуктовому программированию",
  fspCategory: "Backend · Junior · 64 человека",
  fspPlace: "место в категории",
  fspWithout: "без ФСП · топ-45 %",
  fspWith: "с ФСП · топ-30 %",

  numsLabel: "Цифры",
  numsTitle: "Платформа в цифрах",
  numsDemo: "демо",

  finalTitle: "Десять минут до первого приглашения",
  finalNote: "Бесплатно для кандидатов",

  footerAria: "Подвал",
  terms: "Условия",
  privacy: "Политика ПДн",
  contacts: "Контакты",
  contactToast: "По вопросам проекта — капитану команды в Telegram @elo_34",
  contactOpen: "Открыть",
  contactUrl: "https://t.me/elo_34",
  demo: "Демо для жюри",
  copyright: "© 2026 Федерация спортивного программирования. Заглушка подвала.",

  juryTitle: "Для жюри: без регистрации",
  juryCandidate: "Войти как кандидат",
  juryEmployer: "Войти как работодатель",
  juryHide: "свернуть",
  juryShow: "развернуть",
  juryError: "Не удалось войти в демо. Попробуйте ещё раз.",
  juryTry: [
    "Кандидат: пройдите экспресс-тест на 3–5 минут и получите грейд.",
    "Работодатель: найдите кандидата в поиске и откройте анонимную карточку.",
    "Приглашение: отправьте приглашение с вилкой и посмотрите его у кандидата.",
  ],
} as const;

export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

/** Подписи счётчиков блока «Цифры» по числу. */
export const NUM_LABEL = {
  candidates: (n: number) => plural(n, "кандидат", "кандидата", "кандидатов"),
  companies: (n: number) => plural(n, "компания", "компании", "компаний"),
  invitations: (n: number) => plural(n, "приглашение", "приглашения", "приглашений"),
  median_days_to_invite: (n: number) => `${plural(n, "день", "дня", "дней")} до первого приглашения`,
} as const;

/** Панель «что попробовать» (E34-2): сценарий жюри за 5 минут. */
export const PANEL = {
  title: "Что попробовать",
  steps: [
    { to: "/me/assessment?mode=express", label: "Пройти экспресс-тест", who: "Кандидат · 3–5 минут" },
    { to: "/me", label: "Посмотреть грейд и доверие", who: "Кандидат" },
    { to: "/employer", label: "Подобрать кандидатов", who: "Работодатель (вход с лендинга)" },
    { to: "/employer/offers", label: "Отправить приглашение с вилкой", who: "Работодатель" },
    { to: "/me/offers", label: "Открыть приглашение у кандидата", who: "Кандидат" },
  ],
} as const;
