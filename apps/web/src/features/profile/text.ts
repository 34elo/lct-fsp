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
