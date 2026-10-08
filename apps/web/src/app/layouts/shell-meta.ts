import { Building2, LayoutDashboard } from "@fsp/ui";

import { NAV, activeNav, type NavItem } from "@/app/routes";

/** Нижняя панель кандидата — те же четыре пункта, что в шапке (E35-1). */
export const CANDIDATE_BOTTOM: NavItem[] = NAV.candidate;

export const ROLE_LABEL: Record<string, string> = {
  candidate: "Кандидат",
  employer: "Работодатель",
  fsp_admin: "Администратор ФСП",
};

export const ADMIN_ICON = LayoutDashboard;
export const COMPANY_ICON = Building2;

export { NAV, activeNav };

/** Две буквы-инициалы для аватара. */
export function initials(name: string): string {
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}
