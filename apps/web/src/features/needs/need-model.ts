import type { CandidateCard, NeedCategory, TestGrade } from "@/api/model";
import { GRADE_LABEL, ROLE_LABEL } from "@/features/profile/text";

/* Модель экранов потребности: заявлено vs подтверждено и клиентские фильтры/сортировка карточек категории. */

export type ClaimStatus = "match" | "below" | "above" | "none";

const TEST_ORDER = ["junior", "middle", "senior"] as const;

/** Заявленный грейд профиля → уровень теста: intern→junior, *_plus→база, lead→senior. */
export function toTestGrade(grade: string | null | undefined): TestGrade | null {
  if (!grade) return null;
  if (grade === "intern") return "junior";
  if (grade === "lead") return "senior";
  const base = grade.replace(/_plus$/, "");
  return (TEST_ORDER as readonly string[]).includes(base) ? (base as TestGrade) : null;
}

export interface ClaimedVsConfirmed {
  claimed: TestGrade | null;
  confirmed: TestGrade | null;
  status: ClaimStatus;
}

/** Грейд из теста берётся из `categories` карточки по профессии; без него — «подтверждения нет». */
export function claimedVsConfirmed(card: CandidateCard, profession: string): ClaimedVsConfirmed {
  const claimed = toTestGrade(card.grade);
  const confirmed = card.categories?.find((c) => c.profession === profession)?.grade ?? null;
  if (!confirmed) return { claimed, confirmed: null, status: "none" };
  if (!claimed) return { claimed, confirmed, status: "match" };
  const d = TEST_ORDER.indexOf(claimed) - TEST_ORDER.indexOf(confirmed);
  return { claimed, confirmed, status: d === 0 ? "match" : d > 0 ? "below" : "above" };
}

export type CandidateSort = "rank" | "match" | "strength";

export interface CategoryFilters {
  minStrength: number;
  confirmedOnly: boolean;
  fspOnly: boolean;
  remoteOnly: boolean;
  budgetMax: number | null;
  /** Название навыка из топа карточки; null — любой. */
  skill: string | null;
}

export const EMPTY_CATEGORY_FILTERS: CategoryFilters = { minStrength: 0, confirmedOnly: false, fspOnly: false, remoteOnly: false, budgetMax: null, skill: null };

export const isDefaultFilters = (f: CategoryFilters): boolean => JSON.stringify(f) === JSON.stringify(EMPTY_CATEGORY_FILTERS);

/** Фильтр не сбрасывает отмеченных в шорт-лист (E23-5): они остаются в списке при любых условиях. */
export function applyFilters(items: CandidateCard[], f: CategoryFilters, profession: string, shortlist: ReadonlySet<string>): CandidateCard[] {
  return items.filter((c) => {
    if (shortlist.has(c.pseudo_id)) return true;
    if (f.minStrength > 0 && (c.strength?.value ?? 0) < f.minStrength) return false;
    if (f.confirmedOnly && claimedVsConfirmed(c, profession).confirmed === null) return false;
    if (f.fspOnly && c.fsp_highlights.length === 0) return false;
    if (f.remoteOnly && !c.formats.includes("remote")) return false;
    if (f.skill !== null && !c.top_skills.some((x) => x.name === f.skill)) return false;
    if (f.budgetMax !== null && c.salary_min !== null && c.salary_min > f.budgetMax) return false;
    return true;
  });
}

/** «Ранг» — порядок сервера (0,6·совпадение + 0,4·сила), остальное — по убыванию поля. */
export function sortCards(items: CandidateCard[], sort: CandidateSort): CandidateCard[] {
  if (sort === "rank") return items;
  const key = (c: CandidateCard) => (sort === "match" ? (c.match?.score ?? 0) : (c.strength?.value ?? 0));
  return items
    .map((c, i) => ({ c, i }))
    .sort((a, b) => key(b.c) - key(a.c) || a.i - b.i)
    .map((x) => x.c);
}

export const gradeTitle = (g: string): string => GRADE_LABEL[g] ?? g;

export const professionTitle = (slug: string, cats?: NeedCategory[]): string => cats?.find((c) => c.profession === slug)?.title ?? ROLE_LABEL[slug] ?? slug;

export const fixed2 = (v: number): string => v.toFixed(2);
