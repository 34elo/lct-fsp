import type { CandidateCard } from "@/api/model";
import { applyFilters, claimedVsConfirmed, EMPTY_CATEGORY_FILTERS, sortCards, toTestGrade } from "./need-model";

const mk = (id: string, over: Partial<CandidateCard> = {}): CandidateCard =>
  ({
    pseudo_id: id, pseudonym: `Backend #${id}`, avatar_seed: id, primary_role: "backend", grade: "middle", grade_preliminary: false,
    primary_stack: [], top_skills: [], fsp_highlights: [], salary_min: 200000, formats: ["remote"], city: null, relocation: false,
    search_status: "active", updated_at: "2026-10-01T00:00:00Z", categories: [{ profession: "backend", grade: "middle" }],
    strength: { value: 0.5 }, match: { score: 0.5, explanation: [] }, ...over,
  }) as CandidateCard;

describe("claimedVsConfirmed", () => {
  it("сводит заявленный грейд к уровням теста", () => {
    expect(toTestGrade("middle_plus")).toBe("middle");
    expect(toTestGrade("intern")).toBe("junior");
    expect(toTestGrade("lead")).toBe("senior");
    expect(toTestGrade(null)).toBeNull();
  });
  it("совпадает, выше, ниже и без теста", () => {
    expect(claimedVsConfirmed(mk("1"), "backend").status).toBe("match");
    expect(claimedVsConfirmed(mk("2", { grade: "senior" }), "backend").status).toBe("below");
    expect(claimedVsConfirmed(mk("3", { grade: "junior" }), "backend").status).toBe("above");
    expect(claimedVsConfirmed(mk("4", { categories: [] }), "backend")).toMatchObject({ status: "none", confirmed: null });
  });
});

describe("applyFilters", () => {
  const items = [mk("a"), mk("b", { formats: ["office"], salary_min: 300000 }), mk("c", { categories: [], strength: { value: 0.1 } })];
  it("отсекает по условиям", () => {
    const f = { ...EMPTY_CATEGORY_FILTERS, remoteOnly: true, confirmedOnly: true, budgetMax: 250000 };
    expect(applyFilters(items, f, "backend", new Set()).map((c) => c.pseudo_id)).toEqual(["a"]);
  });
  it("не сбрасывает отмеченных в шорт-лист", () => {
    const f = { ...EMPTY_CATEGORY_FILTERS, remoteOnly: true, minStrength: 0.4 };
    expect(applyFilters(items, f, "backend", new Set(["b", "c"])).map((c) => c.pseudo_id)).toEqual(["a", "b", "c"]);
  });
});

describe("sortCards", () => {
  it("по силе профиля, устойчиво", () => {
    const xs = [mk("a", { strength: { value: 0.2 } }), mk("b", { strength: { value: 0.9 } }), mk("c", { strength: { value: 0.2 } })];
    expect(sortCards(xs, "strength").map((c) => c.pseudo_id)).toEqual(["b", "a", "c"]);
    expect(sortCards(xs, "rank")).toBe(xs);
  });
});
