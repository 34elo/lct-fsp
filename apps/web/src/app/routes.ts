import type { Role } from "@/shared/lib/auth";

export type Section = "public" | "auth" | "candidate" | "employer" | "admin";

export interface RouteDef {
  path: string;
  title: string;
  /** Макет из docs/design/screens (для сверки). */
  screen?: string;
  section: Section;
  /** Владелец страницы (blocks.md §4.8). */
  owner: "b1" | "b2";
  /** Пункт навигации: меню строится из routes.ts (blocks.md §4.8). */
  nav?: boolean;
  /** Старый адрес без своего экрана: ведёт на рабочий экран (ссылки на него ещё есть в коде). */
  redirect?: string;
}

/** Карта маршрутов — frontend.md §1. Роль определяется разделом. */
export const ROUTES: RouteDef[] = [
  { path: "/", title: "Лендинг", screen: "L1, L2", section: "public", owner: "b2" },
  { path: "/run/:token", title: "Живой прогон", screen: "Q3", section: "public", owner: "b2" },
  // >>> block1 (public)
  // <<< block1 (public)
  // >>> block2 (public)
  { path: "/jobs", title: "Вакансии", section: "public", owner: "b2" },
  { path: "/jobs/:id", title: "Вакансия", section: "public", owner: "b2" },
  { path: "/terms", title: "Условия", section: "public", owner: "b2" },
  { path: "/privacy", title: "Приватность", section: "public", owner: "b2" },
  // <<< block2 (public)

  { path: "/login", title: "Вход", section: "auth", owner: "b1" },
  { path: "/register", title: "Регистрация", section: "auth", owner: "b1" },
  { path: "/auth/magic", title: "Вход по ссылке", section: "auth", owner: "b1" },
  { path: "/consents", title: "Согласия", screen: "M1", section: "auth", owner: "b1" },
  // >>> block1 (auth)
  { path: "/verify-email", title: "Подтверждение email", section: "auth", owner: "b1" },
  // <<< block1 (auth)
  // >>> block2 (auth)
  // <<< block2 (auth)

  { path: "/onboarding", title: "Онбординг", screen: "M1", section: "candidate", owner: "b1", nav: true },
  { path: "/me", title: "Мой профиль", screen: "D", section: "candidate", owner: "b1", nav: true },
  { path: "/me/graph", title: "Граф доказательств", screen: "G1, G2", section: "candidate", owner: "b1", nav: true },
  { path: "/me/skills/:slug", title: "Доказательства навыка", section: "candidate", owner: "b1" },
  { path: "/me/offers", title: "Приглашения", screen: "M2", section: "candidate", owner: "b2", nav: true },
  { path: "/me/offers/:id", title: "Приглашение", screen: "M2", section: "candidate", owner: "b2" },
  { path: "/me/growth", title: "Рост и тест", section: "candidate", owner: "b1", redirect: "/me/navigator" },
  { path: "/me/settings", title: "Настройки", section: "candidate", owner: "b1", redirect: "/me" },
  // >>> block1 (candidate)
  { path: "/me/assessment", title: "Опрос и грейд", section: "candidate", owner: "b1", nav: true },
  { path: "/me/assessment/history", title: "История тестов", section: "candidate", owner: "b1" },
  { path: "/me/assessment/attempts/:id", title: "Прохождение теста", section: "candidate", owner: "b1" },
  { path: "/me/assessment/attempts/:id/result", title: "Результат теста", section: "candidate", owner: "b1" },
  { path: "/me/tasks", title: "Регулярные задания", section: "candidate", owner: "b1", nav: true },
  { path: "/me/profile/edit", title: "Редактирование профиля", section: "candidate", owner: "b1", nav: true },
  // <<< block1 (candidate)
  // >>> block2 (candidate)
  { path: "/me/responses", title: "Мои отклики", section: "candidate", owner: "b2", nav: true },
  { path: "/me/navigator", title: "Навигатор роста", section: "candidate", owner: "b2" },
  { path: "/me/interests", title: "Вами интересуются", section: "candidate", owner: "b2", nav: true },
  // <<< block2 (candidate)

  { path: "/employer/search", title: "Поиск", screen: "A, E2", section: "employer", owner: "b2", nav: true },
  { path: "/employer/candidates/:id", title: "Карточка кандидата", screen: "B", section: "employer", owner: "b2" },
  { path: "/employer/offers/new", title: "Новое приглашение", screen: "C", section: "employer", owner: "b2" },
  { path: "/employer/vacancies", title: "Вакансии", screen: "E3", section: "employer", owner: "b2", nav: true },
  { path: "/employer/vacancies/new", title: "Новая вакансия", screen: "E3", section: "employer", owner: "b2" },
  { path: "/employer/vacancies/:id", title: "Вакансия", screen: "E3", section: "employer", owner: "b2" },
  { path: "/employer/vacancies/:id/shortlist", title: "Подборка", screen: "E4", section: "employer", owner: "b2" },
  { path: "/employer/offers", title: "Мои приглашения", screen: "E5", section: "employer", owner: "b2", nav: true },
  { path: "/employer/offers/:id", title: "Приглашение", screen: "E5", section: "employer", owner: "b2" },
  { path: "/employer/company", title: "Компания", section: "employer", owner: "b2", nav: true },
  // >>> block1 (employer)
  { path: "/employer/tasks", title: "Задания компании", section: "employer", owner: "b1", nav: true },
  { path: "/employer/families/new", title: "Конструктор задания", section: "employer", owner: "b1" },
  // <<< block1 (employer)
  // >>> block2 (employer)
  { path: "/employer/needs/new", title: "Новая потребность", section: "employer", owner: "b2", nav: true },
  { path: "/employer/needs/:id", title: "Рекомендованные категории", section: "employer", owner: "b2" },
  { path: "/employer/categories/:profession/:grade", title: "Кандидаты категории", section: "employer", owner: "b2" },
  { path: "/employer/responses", title: "Отклики на вакансии", section: "employer", owner: "b2", nav: true },
  { path: "/employer/subscriptions", title: "Подписки на категории", section: "employer", owner: "b2", nav: true },
  // <<< block2 (employer)

  { path: "/federation", title: "Дашборд ФСП", screen: "F1", section: "admin", owner: "b2", nav: true },
  { path: "/federation/moderation", title: "Модерация", screen: "F3", section: "admin", owner: "b2", nav: true },
  { path: "/admin/skills", title: "Граф навыков", screen: "G3", section: "admin", owner: "b1", nav: true },
  { path: "/admin/quality", title: "Качество", screen: "Q1", section: "admin", owner: "b2", nav: true },
  { path: "/admin/quality/fairness", title: "Справедливость", screen: "Q2", section: "admin", owner: "b2" },
  { path: "/admin/quality/runs", title: "Живые прогоны", screen: "Q3", section: "admin", owner: "b2" },
  // >>> block1 (admin)
  { path: "/admin/families", title: "Очередь допуска", section: "admin", owner: "b1", nav: true },
  { path: "/admin/professions", title: "Профессии и навыки", section: "admin", owner: "b1", nav: true },
  { path: "/admin/demo/two-worlds", title: "Два мира", section: "admin", owner: "b1" },
  { path: "/admin/demo/llm-exam", title: "LLM сдаёт тест", section: "admin", owner: "b1" },
  { path: "/admin/demo/new-profession", title: "Новая профессия", section: "admin", owner: "b1" },
  // <<< block1 (admin)
  // >>> block2 (admin)
  // <<< block2 (admin)
];

export const SECTION_ROLE: Partial<Record<Section, Role>> = {
  candidate: "candidate",
  employer: "employer",
  admin: "fsp_admin",
};

export interface NavItem {
  to: string;
  label: string;
  /** Вкладки раздела: строка под шапкой, пока открыт любой из этих путей. */
  tabs?: NavItem[];
  /** Ещё префиксы путей, на которых пункт меню подсвечен. */
  match?: string[];
}

/**
 * Меню по ролям (E35-1, ux-spec §2). Правило: нет пункта меню, ссылки или кнопки без работающего
 * экрана — каждый пункт и вкладка ведут на маршрут с `nav: true` и настоящей страницей (routes.test.ts).
 * «Шорт-лист» работодателя появится в меню вместе с общим экраном (E35-4), «Настройки» и «Согласия»
 * в меню аватара — вместе с экраном настроек (E36-4).
 */
export const NAV: Record<"candidate" | "employer" | "admin", NavItem[]> = {
  candidate: [
    { to: "/me", label: "Главная" },
    { to: "/me/assessment", label: "Тест и грейд" },
    {
      to: "/me/offers",
      label: "Приглашения",
      tabs: [
        { to: "/me/offers", label: "Приглашения" },
        { to: "/me/interests", label: "Вами интересуются" },
        { to: "/me/responses", label: "Отклики" },
      ],
    },
    {
      to: "/me/profile/edit",
      label: "Профиль",
      tabs: [
        { to: "/me/profile/edit", label: "Данные" },
        { to: "/onboarding", label: "Резюме и ФСП" },
        { to: "/me/graph", label: "Граф" },
        { to: "/me/tasks", label: "Задания" },
      ],
    },
  ],
  employer: [
    {
      to: "/employer/search",
      label: "Подбор",
      tabs: [
        { to: "/employer/search", label: "Поиск" },
        { to: "/employer/needs/new", label: "Кого ищете" },
      ],
      match: ["/employer/needs", "/employer/categories", "/employer/candidates"],
    },
    {
      to: "/employer/offers",
      label: "Приглашения",
      tabs: [
        { to: "/employer/offers", label: "Приглашения" },
        { to: "/employer/responses", label: "Отклики" },
      ],
    },
    {
      to: "/employer/company",
      label: "Компания",
      tabs: [
        { to: "/employer/company", label: "Компания" },
        { to: "/employer/vacancies", label: "Вакансии" },
        { to: "/employer/tasks", label: "Задания" },
        { to: "/employer/subscriptions", label: "Подписки" },
      ],
      match: ["/employer/families"],
    },
  ],
  admin: [
    { to: "/federation", label: "Дашборд" },
    { to: "/admin/families", label: "Допуск заданий" },
    { to: "/admin/professions", label: "Профессии" },
    { to: "/admin/skills", label: "Граф навыков" },
    { to: "/federation/moderation", label: "Модерация" },
    { to: "/admin/quality", label: "Качество" },
  ],
};

/** Все пути пункта меню: сам пункт, его вкладки и доп. префиксы. */
const navPaths = (n: NavItem) => [n.to, ...(n.tabs ?? []).map((t) => t.to), ...(n.match ?? [])];

const covers = (prefix: string, pathname: string) => pathname === prefix || pathname.startsWith(`${prefix}/`);

/** Активный пункт меню: тот, чей путь — самый длинный префикс текущего адреса. */
export function activeNav(nav: NavItem[], pathname: string): NavItem | undefined {
  let best: NavItem | undefined;
  let len = -1;
  for (const n of nav)
    for (const p of navPaths(n))
      if (covers(p, pathname) && p.length > len) {
        best = n;
        len = p.length;
      }
  return best;
}
