import { Building2, Handshake, LayoutDashboard, TrendingUp, Trophy, User, type LucideIcon } from "@fsp/ui";

import { NAV, type NavItem } from "@/app/routes";

/** Иконки пунктов нижней панели кандидата (E19-5). */
export const BOTTOM_ICON: Record<string, LucideIcon> = {
  "/me": User,
  "/me/offers": Handshake,
  "/me/growth": TrendingUp,
  "/me/settings": Trophy,
};

/** Нижняя панель кандидата: Профиль, Офферы, Рост, ФСП (привязка ФСП живёт в настройках). */
export const CANDIDATE_BOTTOM: NavItem[] = [
  { to: "/me", label: "Профиль" },
  { to: "/me/offers", label: "Офферы" },
  { to: "/me/growth", label: "Рост" },
  { to: "/me/settings", label: "ФСП" },
];

export const ROLE_LABEL: Record<string, string> = {
  candidate: "Кандидат",
  employer: "Работодатель",
  fsp_admin: "Администратор ФСП",
};

export const ADMIN_ICON = LayoutDashboard;
export const COMPANY_ICON = Building2;

/** Пункты с `end`, чей путь — префикс соседнего (`/me` и `/me/offers`). */
export const isPrefix = (nav: NavItem[], to: string) => nav.some((o) => o.to !== to && o.to.startsWith(`${to}/`));

export { NAV };

/** Две буквы-инициалы для аватара. */
export function initials(name: string): string {
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}
