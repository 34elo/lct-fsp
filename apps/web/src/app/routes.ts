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
}

/** Карта маршрутов — frontend.md §1. Роль определяется разделом. */
export const ROUTES: RouteDef[] = [
  { path: "/", title: "Лендинг", screen: "L1, L2", section: "public", owner: "b2" },
  { path: "/athlete/:id", title: "Публичная карточка", screen: "P1", section: "public", owner: "b2" },
  { path: "/verify/:id", title: "Проверка Open Badge", section: "public", owner: "b2" },
  { path: "/run/:token", title: "Живой прогон", screen: "Q3", section: "public", owner: "b2" },
  // >>> block1 (public)
  // <<< block1 (public)
  // >>> block2 (public)
  { path: "/jobs", title: "Вакансии", section: "public", owner: "b2" },
  { path: "/jobs/:id", title: "Вакансия", section: "public", owner: "b2" },
  // <<< block2 (public)

  { path: "/login", title: "Вход", section: "auth", owner: "b1" },
  { path: "/register", title: "Регистрация", section: "auth", owner: "b1" },
  { path: "/auth/magic", title: "Вход по ссылке", section: "auth", owner: "b1" },
  { path: "/consents", title: "Согласия", screen: "M1", section: "auth", owner: "b1" },
  { path: "/auth/fsp/callback", title: "Вход через ФСП", section: "auth", owner: "b1" },
  // >>> block1 (auth)
  { path: "/verify-email", title: "Подтверждение email", section: "auth", owner: "b1" },
  // <<< block1 (auth)
  // >>> block2 (auth)
  // <<< block2 (auth)

  { path: "/onboarding", title: "Онбординг", screen: "M1", section: "candidate", owner: "b1", nav: true },
  { path: "/me", title: "Мой профиль", screen: "D", section: "candidate", owner: "b1", nav: true },
  { path: "/me/graph", title: "Граф доказательств", screen: "G1, G2", section: "candidate", owner: "b1", nav: true },
  { path: "/me/skills/:slug", title: "Доказательства навыка", section: "candidate", owner: "b1" },
  { path: "/me/offers", title: "Офферы", screen: "M2", section: "candidate", owner: "b2", nav: true },
  { path: "/me/offers/:id", title: "Оффер", screen: "M2", section: "candidate", owner: "b2" },
  { path: "/me/growth", title: "Рост и тест", screen: "M3", section: "candidate", owner: "b1", nav: true },
  { path: "/me/badge", title: "Open Badge", screen: "Q5", section: "candidate", owner: "b1" },
  { path: "/me/settings", title: "Настройки", section: "candidate", owner: "b1", nav: true },
  // >>> block1 (candidate)
  { path: "/me/assessment", title: "Опрос и грейд", section: "candidate", owner: "b1", nav: true },
  { path: "/me/assessment/history", title: "История тестов", section: "candidate", owner: "b1" },
  { path: "/me/assessment/attempts/:id", title: "Прохождение теста", section: "candidate", owner: "b1" },
  { path: "/me/assessment/attempts/:id/result", title: "Результат теста", section: "candidate", owner: "b1" },
  { path: "/me/tasks", title: "Регулярные задания", section: "candidate", owner: "b1", nav: true },
  { path: "/me/profile/edit", title: "Редактирование профиля", section: "candidate", owner: "b1" },
  // <<< block1 (candidate)
  // >>> block2 (candidate)
  { path: "/me/responses", title: "Мои отклики", section: "candidate", owner: "b2", nav: true },
  { path: "/me/navigator", title: "Навигатор роста", section: "candidate", owner: "b2", nav: true },
  { path: "/me/interests", title: "Вами интересуются", section: "candidate", owner: "b2", nav: true },
  // <<< block2 (candidate)

  { path: "/employer/market", title: "Рынок талантов", screen: "E1", section: "employer", owner: "b2", nav: true },
  { path: "/employer/search", title: "Поиск", screen: "A, E2", section: "employer", owner: "b2", nav: true },
  { path: "/employer/candidates/:id", title: "Карточка кандидата", screen: "B", section: "employer", owner: "b2" },
  { path: "/employer/candidates/:id/graph", title: "Граф кандидата", screen: "G1", section: "employer", owner: "b2" },
  { path: "/employer/candidates/:id/interview", title: "Интервью", screen: "Q4", section: "employer", owner: "b2" },
  { path: "/employer/offers/new", title: "Новый оффер", screen: "C", section: "employer", owner: "b2" },
  { path: "/employer/vacancies", title: "Вакансии", screen: "E3", section: "employer", owner: "b2", nav: true },
  { path: "/employer/vacancies/:id", title: "Вакансия", screen: "E3", section: "employer", owner: "b2" },
  { path: "/employer/vacancies/:id/shortlist", title: "Подборка", screen: "E4", section: "employer", owner: "b2" },
  { path: "/employer/offers", title: "Мои офферы", screen: "E5", section: "employer", owner: "b2", nav: true },
  { path: "/employer/offers/:id", title: "Оффер", screen: "E5", section: "employer", owner: "b2" },
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
  { path: "/federation/matrix", title: "Матрица дисциплин", screen: "F2", section: "admin", owner: "b2", nav: true },
  { path: "/federation/moderation", title: "Модерация", screen: "F3", section: "admin", owner: "b2", nav: true },
  { path: "/federation/demo", title: "Демо-пульт", screen: "F4", section: "admin", owner: "b2", nav: true },
  { path: "/admin/skills", title: "Граф навыков", screen: "G3", section: "admin", owner: "b1", nav: true },
  { path: "/admin/quality", title: "Качество", screen: "Q1", section: "admin", owner: "b2", nav: true },
  { path: "/admin/quality/fairness", title: "Справедливость", screen: "Q2", section: "admin", owner: "b2" },
  { path: "/admin/quality/runs", title: "Живые прогоны", screen: "Q3", section: "admin", owner: "b2" },
  { path: "/admin/health", title: "Здоровье", screen: "Q6", section: "admin", owner: "b2", nav: true },
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
  /** Не помещается в нижнюю панель на 375 px: только в верхнем меню. */
  desktopOnly?: boolean;
}

export const NAV: Record<"candidate" | "employer" | "admin", NavItem[]> = {
  candidate: [
    { to: "/me", label: "Профиль" },
    { to: "/me/offers", label: "Офферы" },
    { to: "/me/interests", label: "Интересуются", desktopOnly: true },
    { to: "/me/responses", label: "Отклики", desktopOnly: true },
    { to: "/onboarding", label: "Резюме" },
    { to: "/me/graph", label: "Граф" },
    { to: "/me/growth", label: "Рост" },
    { to: "/me/navigator", label: "Навигатор", desktopOnly: true },
    { to: "/me/settings", label: "Настройки", desktopOnly: true },
  ],
  employer: [
    { to: "/employer/market", label: "Рынок" },
    { to: "/employer/search", label: "Поиск" },
    { to: "/employer/vacancies", label: "Вакансии" },
    { to: "/employer/responses", label: "Отклики" },
    { to: "/employer/offers", label: "Офферы" },
    { to: "/employer/subscriptions", label: "Подписки" },
    { to: "/employer/company", label: "Компания" },
  ],
  admin: [
    { to: "/federation", label: "Дашборд" },
    { to: "/federation/matrix", label: "Матрица" },
    { to: "/federation/moderation", label: "Модерация" },
    { to: "/federation/demo", label: "Демо" },
    { to: "/admin/skills", label: "Навыки" },
    { to: "/admin/quality", label: "Качество" },
    { to: "/admin/health", label: "Здоровье" },
  ],
};
