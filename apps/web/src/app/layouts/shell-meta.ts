import { NAV, activeNav, type NavItem } from "@/app/routes";

/** Нижняя панель на телефоне — пять пунктов (шестой не помещается в 375 px): у кандидата «Статистика» открывается с Главной. */
export const CANDIDATE_BOTTOM: NavItem[] = NAV.candidate.filter((n) => n.to !== "/me/stats");

/** Нижняя панель работодателя: «Задания» открываются со страницы «Компания». */
export const EMPLOYER_BOTTOM: NavItem[] = NAV.employer.filter((n) => n.to !== "/employer/tasks");

export const ROLE_LABEL: Record<string, string> = {
  candidate: "Кандидат",
  employer: "Работодатель",
  fsp_admin: "Администратор ФСП",
};


export { NAV, activeNav };

/** Две буквы-инициалы для аватара. */
export function initials(name: string): string {
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}
