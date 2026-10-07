import type { CandidateCard, NeedCategory, SubscriptionOut } from "@/api/model";
import { catKey, categoryStats, feedTime, loadLastNeed, pickCategory, salaryShort, saveLastNeed, subscriptionTerms, subscriptionTitle, toMatchCard } from "./match-model";

const cat = (p: string, g: string, n: number): NeedCategory => ({ profession: p, title: p, grade: g, affinity: 0.8, candidates: n, median_salary: 220000, fsp_share: 0.24 });

const card: CandidateCard = {
  pseudo_id: "p1", pseudonym: "Backend #3377", avatar_seed: "x", primary_role: "backend", grade: "middle", grade_preliminary: false,
  primary_stack: [], fsp_highlights: [], salary_min: 190000, formats: ["remote"], city: null, relocation: false, search_status: "active",
  updated_at: "2026-10-02T00:00:00Z", match: { score: 0.94, explanation: [] }, categories: [{ profession: "backend", grade: "middle" }],
  top_skills: [
    { slug: "python", name: "Python", level: 3, sources: ["test"] },
    { slug: "postgresql", name: "PostgreSQL", level: 2, sources: ["github"] },
    { slug: "docker", name: "Docker", level: 0, sources: ["resume"] },
    { slug: "git", name: "Git", level: 1, sources: ["test"] },
  ],
};

test("выбранная категория: из ?cat, иначе первая непустая", () => {
  const cats = [cat("backend", "middle", 0), cat("backend", "junior", 5), cat("qa", "junior", 3)];
  expect(catKey(pickCategory(cats, "qa:junior")!)).toBe("qa:junior");
  expect(catKey(pickCategory(cats, null)!)).toBe("backend:junior");
  expect(pickCategory([], null)).toBeNull();
});

test("строка категории: люди, медиана, доля ФСП; пустая — прочерки", () => {
  expect(categoryStats(cat("backend", "middle", 37))).toEqual({ people: "37", median: (220000).toLocaleString("ru-RU"), fsp: "24 %" });
  expect(categoryStats({ ...cat("qa", "junior", 0), median_salary: null, fsp_share: null })).toMatchObject({ median: "—", fsp: "—" });
});

test("карточка совпадения: подтверждённый грейд, три навыка, заявленный — пунктиром", () => {
  const d = toMatchCard(card, "backend");
  expect(d).toMatchObject({ pseudonym: "Backend #3377", match: 94, grade: "Middle", confirmed: true });
  expect(d.skills.map((s) => [s.name, s.claimed])).toEqual([["Python", false], ["PostgreSQL", false], ["Docker", true]]);
  expect(d.meta).toBe("Удалённо · 3 навыка подтверждены");
  expect(d.salary).toMatch(/^от 190/);
  // Тест по другой профессии — грейд заявлен.
  expect(toMatchCard(card, "frontend").confirmed).toBe(false);
  expect(salaryShort(card)).toBe("от 190");
  expect(salaryShort({ ...card, salary_min: null })).toBe("—");
});

test("подписка: категория и условия", () => {
  const s: SubscriptionOut = { id: "s1", profession: "backend", grades: ["junior"], skills: [], salary_max: null, formats: [], only_confirmed: true, created_at: "2026-10-01T00:00:00Z" };
  expect(subscriptionTitle(s)).toBe("Backend · Junior");
  expect(subscriptionTerms(s)).toBe("любые условия");
  expect(subscriptionTitle({ ...s, grades: [] })).toBe("Backend · любой грейд");
  expect(subscriptionTerms({ ...s, salary_max: 220000, formats: ["remote"] })).toMatch(/^до 220.000.₽ · Удалённо$/);
});

test("время ленты: сегодня — часы, раньше — дата", () => {
  const now = new Date(2026, 9, 8, 12, 0);
  expect(feedTime(new Date(2026, 9, 8, 10, 12).toISOString(), now)).toBe("10:12");
  expect(feedTime(new Date(2026, 9, 6, 23, 5).toISOString(), now)).toBe("06.10");
});

test("последний запрос хранится в браузере и стирается", () => {
  saveLastNeed({ id: "n1", text: "Backend", chips: ["Backend"] });
  expect(loadLastNeed()).toEqual({ id: "n1", text: "Backend", chips: ["Backend"] });
  saveLastNeed(null);
  expect(loadLastNeed()).toBeNull();
  localStorage.setItem("fsp.employer.lastNeed", "{oops");
  expect(loadLastNeed()).toBeNull();
});
