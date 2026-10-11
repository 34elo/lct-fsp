import type { SkillWithTrust } from "@/api/model";

import { sortSkills } from "./home-model";

/** Сколько навыков на вкладке «Навыки» по умолчанию. */
export const SKILLS_TOP = 15;

export type SkillState = "all" | "confirmed" | "claimed";

export interface SkillFilter {
  q: string;
  /** Тип навыка (`SkillType`), `null` — любой. */
  type: string | null;
  /** Минимальное доверие 0..4 (точки). */
  trust: number;
  state: SkillState;
  showHidden: boolean;
}

export const NO_FILTER: SkillFilter = { q: "", type: null, trust: 0, state: "all", showHidden: false };

/** Доверие навыка в точках: заявленное без доказательств — 0. */
export const trustOf = (s: SkillWithTrust) => (s.claimed_only ? 0 : Math.max(0, Math.min(4, Math.round(s.level))));

/** Фильтр включён (что-то кроме значений по умолчанию). */
export const isFiltered = (f: SkillFilter) => f.q.trim() !== "" || f.type !== null || f.trust > 0 || f.state !== "all";

/** Типы навыков, которые есть в профиле, — варианты фильтра (без пустых). */
export function skillTypes(skills: SkillWithTrust[]): string[] {
  return [...new Set(skills.map((s) => s.skill.type).filter((t): t is string => !!t))].sort();
}

/**
 * Навыки вкладки по фильтру: сначала сильнейшие (как на Главной). Скрытые от компаний — только при
 * `showHidden`. Поиск — по названию и slug без учёта регистра.
 */
export function filterSkills(skills: SkillWithTrust[], hidden: ReadonlySet<string>, f: SkillFilter): SkillWithTrust[] {
  const q = f.q.trim().toLocaleLowerCase("ru");
  return sortSkills(skills).filter((s) => {
    if (!f.showHidden && hidden.has(s.skill.slug)) return false;
    if (q && !s.skill.name.toLocaleLowerCase("ru").includes(q) && !s.skill.slug.includes(q)) return false;
    if (f.type && s.skill.type !== f.type) return false;
    if (f.trust > 0 && trustOf(s) < f.trust) return false;
    if (f.state === "confirmed" && s.claimed_only) return false;
    if (f.state === "claimed" && !s.claimed_only) return false;
    return true;
  });
}

/** Новый список скрытых навыков после переключения одного. */
export function toggleHidden(hidden: readonly string[], slug: string): string[] {
  return hidden.includes(slug) ? hidden.filter((x) => x !== slug) : [...hidden, slug].sort();
}
