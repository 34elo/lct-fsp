import { formatRub, type CandidateCardV2Data } from "@fsp/ui";

import type { CandidateCard, NeedCategory, SubscriptionOut } from "@/api/model";
import { claimedVsConfirmed, gradeTitle } from "@/features/needs/need-model";
import { GRADE_LABEL, ROLE_LABEL } from "@/features/profile/text";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import { FORMAT_LABEL, MATCH_TEXT as T, percent } from "./text";

/* Модель экрана «Подбор» (E38-8): категории потребности, карточки лучших совпадений, подписки, лента. */

export const catKey = (c: Pick<NeedCategory, "profession" | "grade">): string => `${c.profession}:${c.grade}`;

/** Выбранная категория: из `?cat=`, иначе первая непустая (сервер отдаёт по совпадению), иначе первая. */
export function pickCategory(cats: NeedCategory[], key: string | null): NeedCategory | null {
  return cats.find((c) => catKey(c) === key) ?? cats.find((c) => c.candidates > 0) ?? cats[0] ?? null;
}

export const categoryTitle = (c: NeedCategory): string => `${c.title} · ${gradeTitle(c.grade)}`;

/** «37 чел · 220 000 · 24 % ФСП»: числа отдельно, чтобы выделить их цветом. */
export function categoryStats(c: NeedCategory): { people: string; median: string; fsp: string } {
  return {
    people: String(c.candidates),
    median: c.median_salary ? c.median_salary.toLocaleString("ru-RU") : "—",
    fsp: c.fsp_share === null || c.fsp_share === undefined ? "—" : `${Math.round(c.fsp_share * 100)} %`,
  };
}

const isClaimedSkill = (sources: string[]) => sources.length === 0 || sources.every((x) => x === "resume" || x === "self");

const capitalize = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s);

/** Анонимная карточка API → CandidateCardV2: грейд подтверждён, если тест дал категорию по этой профессии. */
export function toMatchCard(card: CandidateCard, profession: string): CandidateCardV2Data {
  const cv = claimedVsConfirmed(card, profession);
  const grade = cv.confirmed ?? card.grade;
  const skills = card.top_skills.slice(0, 3).map((s) => ({ name: s.name, level: s.level, claimed: isClaimedSkill(s.sources) }));
  const confirmedSkills = card.top_skills.filter((s) => !isClaimedSkill(s.sources)).length;
  const formats = capitalize(card.formats.map((f) => FORMAT_LABEL[f] ?? f).join(" или "));
  const meta = [formats || null, card.city, confirmedSkills > 0 ? T.confirmedCount(confirmedSkills) : null].filter(Boolean).join(" · ");
  return {
    pseudonym: displayPseudonym(card.pseudonym, profession || card.primary_role),
    // Без вакансии `match` нет: совпадение с запросом в категории — `rank` (0.6·покрытие + 0.4·сила).
    match: card.match ? percent(card.match.score) : card.strength?.rank != null ? percent(card.strength.rank) : 0,
    grade: grade ? (GRADE_LABEL[grade] ?? grade) : T.noGrade,
    confirmed: cv.confirmed !== null,
    salary: card.salary_min ? T.from(formatRub(card.salary_min)) : undefined,
    skills,
    meta: meta || undefined,
  };
}

/** Ожидания в таблице «Ещё N», тыс. ₽: «от 180». */
export const salaryShort = (card: CandidateCard): string => (card.salary_min ? T.from(String(Math.round(card.salary_min / 1000))) : "—");

export function subscriptionTitle(s: SubscriptionOut): string {
  const grades = s.grades.map(gradeTitle).join(", ");
  return `${ROLE_LABEL[s.profession] ?? s.profession} · ${grades || T.anyGrade}`;
}

export function subscriptionTerms(s: SubscriptionOut): string {
  const parts = [s.salary_max ? T.upTo(formatRub(s.salary_max)) : null, ...s.formats.map((f) => FORMAT_LABEL[f] ?? f)].filter(Boolean);
  return parts.join(" · ") || T.anyTerms;
}

const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
const two = (n: number) => String(n).padStart(2, "0");

/** Время события ленты: сегодня — «10:12», раньше — «06.10». */
export function feedTime(at: string, now: Date = new Date()): string {
  const d = new Date(at);
  return sameDay(d, now) ? `${two(d.getHours())}:${two(d.getMinutes())}` : `${two(d.getDate())}.${two(d.getMonth() + 1)}`;
}

export const isToday = (at: string, now: Date = new Date()): boolean => sameDay(new Date(at), now);

/* Последний запрос работодателя — удобство одного браузера: при следующем входе «Ваши категории» уже есть.
   Хранилище может быть недоступно (приватный режим) — тогда экран просто начинается с примеров. */

export interface LastNeed {
  id: string;
  text: string;
  chips: string[];
  /** Компания, чей это запрос: чужой запрос из того же браузера не читаем (иначе 404 в консоли). */
  company?: string;
  /** Условия поиска в URL (E39-21): по ним экран восстанавливает чипсы и фильтры. */
  qs?: string;
}

const LAST_NEED_KEY = "fsp.employer.lastNeed";

export function loadLastNeed(companyId?: string): LastNeed | null {
  try {
    const raw = localStorage.getItem(LAST_NEED_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<LastNeed>;
    if (typeof v.id !== "string") return null;
    if (companyId && v.company !== companyId) return null;
    return { id: v.id, text: v.text ?? "", chips: Array.isArray(v.chips) ? v.chips : [], company: v.company, qs: typeof v.qs === "string" ? v.qs : undefined };
  } catch {
    return null;
  }
}

export function saveLastNeed(v: LastNeed | null): void {
  try {
    if (v) localStorage.setItem(LAST_NEED_KEY, JSON.stringify(v));
    else localStorage.removeItem(LAST_NEED_KEY);
  } catch {
    /* хранилище недоступно — работаем без памяти */
  }
}

/* Онбординг компании пройден или пропущен — больше не показываем сам (кнопка «Начать настройку» остаётся). */
const ONBOARDING_KEY = "fsp.employer.onboardingSkipped";

export function onboardingSkipped(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_KEY) === "1";
  } catch {
    return false;
  }
}

export function setOnboardingSkipped(v: boolean): void {
  try {
    if (v) localStorage.setItem(ONBOARDING_KEY, "1");
    else localStorage.removeItem(ONBOARDING_KEY);
  } catch {
    /* хранилище недоступно — спросим снова при следующем входе */
  }
}
