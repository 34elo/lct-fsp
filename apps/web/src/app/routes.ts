import type { Role } from "@/shared/lib/auth";

export type Section = "public" | "auth" | "candidate" | "employer" | "admin";

export interface RouteDef {
  path: string;
  title: string;
  /** Макет из docs/design/screens (для сверки). */
  screen?: string;
  section: Section;
}

/** Карта маршрутов — frontend.md §1. Роль определяется разделом. */
export const ROUTES: RouteDef[] = [
  { path: "/", title: "Лендинг", screen: "L1, L2", section: "public" },
  { path: "/athlete/:id", title: "Публичная карточка", screen: "P1", section: "public" },
  { path: "/verify/:id", title: "Проверка Open Badge", section: "public" },
  { path: "/run/:token", title: "Живой прогон", screen: "Q3", section: "public" },

  { path: "/login", title: "Вход", section: "auth" },
  { path: "/register", title: "Регистрация", section: "auth" },
  { path: "/auth/magic", title: "Вход по ссылке", section: "auth" },
  { path: "/consents", title: "Согласия", screen: "M1", section: "auth" },
  { path: "/auth/fsp/callback", title: "Вход через ФСП", section: "auth" },

  { path: "/onboarding", title: "Онбординг", screen: "M1", section: "candidate" },
  { path: "/me", title: "Мой профиль", screen: "D", section: "candidate" },
  { path: "/me/graph", title: "Граф доказательств", screen: "G1, G2", section: "candidate" },
  { path: "/me/skills/:slug", title: "Доказательства навыка", section: "candidate" },
  { path: "/me/offers", title: "Офферы", screen: "M2", section: "candidate" },
  { path: "/me/offers/:id", title: "Оффер", screen: "M2", section: "candidate" },
  { path: "/me/growth", title: "Рост и тест", screen: "M3", section: "candidate" },
  { path: "/me/badge", title: "Open Badge", screen: "Q5", section: "candidate" },
  { path: "/me/settings", title: "Настройки", section: "candidate" },

  { path: "/employer/market", title: "Рынок талантов", screen: "E1", section: "employer" },
  { path: "/employer/search", title: "Поиск", screen: "A, E2", section: "employer" },
  { path: "/employer/candidates/:id", title: "Карточка кандидата", screen: "B", section: "employer" },
  { path: "/employer/candidates/:id/graph", title: "Граф кандидата", screen: "G1", section: "employer" },
  { path: "/employer/candidates/:id/interview", title: "Интервью", screen: "Q4", section: "employer" },
  { path: "/employer/offers/new", title: "Новый оффер", screen: "C", section: "employer" },
  { path: "/employer/vacancies", title: "Вакансии", screen: "E3", section: "employer" },
  { path: "/employer/vacancies/:id", title: "Вакансия", screen: "E3", section: "employer" },
  { path: "/employer/vacancies/:id/shortlist", title: "Подборка", screen: "E4", section: "employer" },
  { path: "/employer/offers", title: "Мои офферы", screen: "E5", section: "employer" },
  { path: "/employer/offers/:id", title: "Оффер", screen: "E5", section: "employer" },
  { path: "/employer/company", title: "Компания", section: "employer" },

  { path: "/federation", title: "Дашборд ФСП", screen: "F1", section: "admin" },
  { path: "/federation/matrix", title: "Матрица дисциплин", screen: "F2", section: "admin" },
  { path: "/federation/moderation", title: "Модерация", screen: "F3", section: "admin" },
  { path: "/federation/demo", title: "Демо-пульт", screen: "F4", section: "admin" },
  { path: "/admin/skills", title: "Граф навыков", screen: "G3", section: "admin" },
  { path: "/admin/quality", title: "Качество", screen: "Q1", section: "admin" },
  { path: "/admin/quality/fairness", title: "Справедливость", screen: "Q2", section: "admin" },
  { path: "/admin/quality/runs", title: "Живые прогоны", screen: "Q3", section: "admin" },
  { path: "/admin/health", title: "Здоровье", screen: "Q6", section: "admin" },
];

export const SECTION_ROLE: Partial<Record<Section, Role>> = {
  candidate: "candidate",
  employer: "employer",
  admin: "fsp_admin",
};

export const NAV: Record<"candidate" | "employer" | "admin", { to: string; label: string }[]> = {
  candidate: [
    { to: "/me", label: "Профиль" },
    { to: "/me/graph", label: "Граф" },
    { to: "/me/offers", label: "Офферы" },
    { to: "/me/growth", label: "Рост" },
    { to: "/me/settings", label: "Настройки" },
  ],
  employer: [
    { to: "/employer/market", label: "Рынок" },
    { to: "/employer/search", label: "Поиск" },
    { to: "/employer/vacancies", label: "Вакансии" },
    { to: "/employer/offers", label: "Офферы" },
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
