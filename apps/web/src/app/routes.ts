import type { Role } from "@/shared/lib/auth";

export type Section = "public" | "auth" | "candidate" | "employer" | "admin";

export interface RouteDef {
  path: string;
  title: string;
  section: Section;
  /** Пункт навигации: меню строится из routes.ts. */
  nav?: boolean;
  /** Старый адрес без своего экрана: ведёт на рабочий экран (ссылки на него ещё есть в коде). */
  redirect?: string;
}

/** Карта маршрутов. Роль определяется разделом. */
export const ROUTES: RouteDef[] = [
  { path: "/", title: "Лендинг", section: "public" },
  { path: "/run/:token", title: "Живой прогон", section: "public" },
  { path: "/jobs", title: "Вакансии", section: "public", nav: true },
  { path: "/jobs/:id", title: "Вакансия", section: "public" },
  { path: "/terms", title: "Условия", section: "public" },
  { path: "/privacy", title: "Приватность", section: "public" },
  { path: "/invite/company/:token", title: "Приглашение в команду", section: "public" },

  { path: "/login", title: "Вход", section: "auth" },
  { path: "/register", title: "Регистрация", section: "auth" },
  { path: "/auth/magic", title: "Вход по ссылке", section: "auth" },
  { path: "/consents", title: "Согласия", section: "auth" },
  { path: "/verify-email", title: "Подтверждение email", section: "auth" },
  { path: "/password/new", title: "Новый пароль", section: "auth" },

  { path: "/onboarding", title: "Онбординг", section: "candidate" },
  { path: "/me", title: "Главная", section: "candidate", nav: true },
  // Граф переехал во вкладку профиля.
  { path: "/me/graph", title: "Граф доказательств", section: "candidate", redirect: "/me/profile?tab=graph" },
  { path: "/me/skills/:slug", title: "Доказательства навыка", section: "candidate" },
  { path: "/me/offers", title: "Приглашения", section: "candidate", nav: true },
  { path: "/me/offers/:id", title: "Приглашение", section: "candidate" },
  { path: "/me/growth", title: "Рост и тест", section: "candidate", redirect: "/me/navigator" },
  // Настройки: пункт меню аватара, не вкладка.
  { path: "/me/settings", title: "Настройки", section: "candidate", redirect: "/settings" },
  // Общий для всех ролей: раздел только для карты, каркас выбирается по роли (AccountLayout).
  { path: "/settings", title: "Настройки", section: "candidate" },
  { path: "/me/assessment", title: "Тест и грейд", section: "candidate", nav: true },
  { path: "/me/assessment/history", title: "История тестов", section: "candidate" },
  { path: "/me/assessment/attempts/:id", title: "Прохождение теста", section: "candidate" },
  { path: "/me/assessment/attempts/:id/result", title: "Результат теста", section: "candidate" },
  { path: "/me/assessment/attempts/:id/review", title: "Разбор теста", section: "candidate" },
  { path: "/me/tasks", title: "Регулярные задания", section: "candidate" },
  { path: "/me/profile", title: "Мой профиль", section: "candidate", nav: true },
  { path: "/me/profile/edit", title: "Редактирование профиля", section: "candidate" },
  // Статистика: пункт меню, ссылка есть и на Главной.
  { path: "/me/stats", title: "Статистика", section: "candidate", nav: true },
  // Интересы и отклики — фильтр на странице «Приглашения».
  { path: "/me/responses", title: "Мои отклики", section: "candidate", redirect: "/me/offers?show=responses" },
  { path: "/me/navigator", title: "Навигатор роста", section: "candidate" },
  { path: "/me/interests", title: "Вами интересуются", section: "candidate", redirect: "/me/offers?show=interests" },

  { path: "/employer/search", title: "Поиск", section: "employer" },
  { path: "/employer/candidates/:id", title: "Карточка кандидата", section: "employer" },
  { path: "/employer/offers/new", title: "Новое приглашение", section: "employer" },
  { path: "/employer/vacancies", title: "Вакансии", section: "employer", nav: true },
  { path: "/employer/vacancies/new", title: "Новая вакансия", section: "employer" },
  { path: "/employer/vacancies/:id", title: "Вакансия", section: "employer" },
  { path: "/employer/vacancies/:id/shortlist", title: "Подборка", section: "employer" },
  { path: "/employer/offers", title: "Мои приглашения", section: "employer", nav: true },
  { path: "/employer/offers/:id", title: "Приглашение", section: "employer" },
  { path: "/employer/company", title: "Компания", section: "employer", nav: true },
  { path: "/employer/tasks", title: "Задания компании", section: "employer", nav: true },
  { path: "/employer/families/new", title: "Конструктор задания", section: "employer" },
  { path: "/employer/families/guide", title: "Как сделать задание", section: "employer" },
  { path: "/employer", title: "Подбор", section: "employer", nav: true },
  { path: "/employer/needs/new", title: "Новая потребность", section: "employer" },
  { path: "/employer/needs/:id", title: "Рекомендованные категории", section: "employer" },
  { path: "/employer/categories/:profession/:grade", title: "Кандидаты категории", section: "employer" },
  { path: "/employer/shortlist", title: "Шорт-лист", section: "employer", nav: true },
  // Отклики — фильтр на странице «Приглашения».
  { path: "/employer/responses", title: "Отклики на вакансии", section: "employer", redirect: "/employer/offers?show=responses" },
  // Подписки — блок «Ваши категории» в Подборе, управление открывается из него.
  { path: "/employer/subscriptions", title: "Подписки на категории", section: "employer" },

  // Главная админки: «Что требует вас» и что работает само; воронка — /federation/funnel.
  { path: "/federation", title: "Главная", section: "admin", nav: true },
  { path: "/federation/moderation", title: "Модерация", section: "admin", nav: true },
  { path: "/admin/skills", title: "Граф навыков", section: "admin", nav: true },
  // «Качество» заменено «Аналитикой»: старые адреса ведут на неё.
  { path: "/admin/quality", title: "Качество", section: "admin", redirect: "/federation/analytics" },
  { path: "/admin/quality/fairness", title: "Справедливость", section: "admin", redirect: "/federation/analytics" },
  { path: "/admin/quality/runs", title: "Живые прогоны", section: "admin", redirect: "/federation/analytics" },
  { path: "/admin/families", title: "Допуск заданий", section: "admin", nav: true },
  { path: "/admin/professions", title: "Профессии и навыки", section: "admin", nav: true },
  { path: "/admin/demo/two-worlds", title: "Два мира", section: "admin" },
  { path: "/admin/demo/llm-exam", title: "LLM сдаёт тест", section: "admin" },
  { path: "/admin/demo/new-profession", title: "Новая профессия", section: "admin" },
  // Меню админки по группам: реестр — справочник, заявки — очередь, воронка — аналитика.
  { path: "/federation/registry", title: "Реестр ФСП", section: "admin", nav: true },
  // Заявки — вкладка реестра, старый адрес ведёт на неё.
  { path: "/federation/requests", title: "Заявки ФСП", section: "admin", redirect: "/federation/registry?tab=requests" },
  { path: "/federation/funnel", title: "Воронка", section: "admin", nav: true },
  { path: "/federation/analytics", title: "Аналитика", section: "admin", nav: true },
];

export const SECTION_ROLE: Partial<Record<Section, Role>> = {
  candidate: "candidate",
  employer: "employer",
  admin: "fsp_admin",
};

export type AdminGroup = "queues" | "refs" | "analytics";

/** Группы меню админки: порядок и подписи. */
export const ADMIN_GROUPS: { id: AdminGroup; label: string }[] = [
  { id: "queues", label: "Очереди" },
  { id: "refs", label: "Справочники" },
  { id: "analytics", label: "Аналитика" },
];

export interface NavItem {
  to: string;
  label: string;
  /** Группа пункта в меню админки; без группы — «Главная» над группами. */
  group?: AdminGroup;
  /** Ещё префиксы путей, на которых пункт меню подсвечен. */
  match?: string[];
}

/**
 * Меню по ролям. Правило: нет пункта меню, ссылки или кнопки без работающего
 * экрана — каждый пункт и вкладка ведут на маршрут с `nav: true` и настоящей страницей (routes.test.ts).
 * «Настройки» и «Согласия»
 * в меню аватара — вместе с экраном настроек.
 */
export const NAV: Record<"candidate" | "employer" | "admin", NavItem[]> = {
  candidate: [
    // Регулярные задания открываются с Главной, когда они есть.
    { to: "/me", label: "Главная", match: ["/me/tasks"] },
    { to: "/me/assessment", label: "Тест" },
    // «Интересы» и «Отклики» — фильтр внутри страницы.
    { to: "/me/offers", label: "Приглашения", match: ["/me/interests", "/me/responses"] },
    { to: "/jobs", label: "Вакансии" },
    { to: "/me/stats", label: "Статистика" },
    // Резюме, ФСП и данные — вкладка «Данные» профиля; /onboarding в меню нет.
    { to: "/me/profile", label: "Профиль" },
  ],
  employer: [
    // Подбор: «Поиск» и «Кого ищете» заменяет строка запроса; подписки — блок «Ваши категории».
    { to: "/employer", label: "Подбор", match: ["/employer/subscriptions"] },
    { to: "/employer/shortlist", label: "Шорт-лист" },
    { to: "/employer/offers", label: "Приглашения", match: ["/employer/responses"] },
    { to: "/employer/vacancies", label: "Вакансии" },
    { to: "/employer/tasks", label: "Задания", match: ["/employer/families"] },
    { to: "/employer/company", label: "Компания" },
  ],
  // Админка: «Главная» и три группы — где нужно решение, что админ ведёт, что смотрит.
  admin: [
    { to: "/federation", label: "Главная" },
    { to: "/admin/families", label: "Допуск заданий", group: "queues" },
    { to: "/federation/moderation", label: "Модерация", group: "queues" },
    { to: "/federation/registry", label: "Реестр ФСП", group: "refs" },
    { to: "/admin/professions", label: "Профессии", group: "refs" },
    { to: "/admin/skills", label: "Граф навыков", group: "refs" },
    { to: "/federation/funnel", label: "Воронка", group: "analytics" },
    { to: "/federation/analytics", label: "Аналитика", group: "analytics" },
  ],
};

/** Все пути пункта меню: сам пункт, его вкладки и доп. префиксы. */
const navPaths = (n: NavItem) => [n.to, ...(n.match ?? [])];

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
