import type { CandidateCard } from "@/api/model";
import { splitConfirmed, stackOptions, toRankedCard } from "./category-model";

const card = (o: Partial<CandidateCard>): CandidateCard =>
  ({
    pseudo_id: "p",
    pseudonym: "Backend #1",
    avatar_seed: "x",
    primary_role: "backend",
    grade: "middle",
    grade_preliminary: false,
    primary_stack: [],
    top_skills: [{ slug: "python", name: "Python", level: 3, sources: ["fsp"] }],
    fsp_highlights: [],
    salary_min: 200000,
    formats: ["remote"],
    city: "Москва",
    relocation: false,
    search_status: "active",
    updated_at: "2026-10-02T00:00:00Z",
    categories: [{ profession: "backend", grade: "middle" }],
    ...o,
  }) as CandidateCard;

describe("category-model", () => {
  it("splitConfirmed: без теста по профессии — в неподтверждённые, порядок сохраняется", () => {
    const a = card({ pseudo_id: "a" });
    const b = card({ pseudo_id: "b", categories: [] });
    const c = card({ pseudo_id: "c" });
    const r = splitConfirmed([a, b, c], "backend");
    expect(r.confirmed.map((x) => x.pseudo_id)).toEqual(["a", "c"]);
    expect(r.unconfirmed.map((x) => x.pseudo_id)).toEqual(["b"]);
  });

  it("stackOptions: по частоте, затем по алфавиту", () => {
    const sk = (name: string) => ({ slug: name, name, level: 1, sources: [] });
    const r = stackOptions([card({ top_skills: [sk("Go"), sk("Python")] }), card({ top_skills: [sk("Python")] })]);
    expect(r).toEqual(["Python", "Go"]);
  });

  it("toRankedCard: сила, ФСП и факты «почему» (не больше трёх)", () => {
    const r = toRankedCard(
      card({
        strength: { value: 0.71, rank: 0.8 },
        fsp_highlights: [{ title: "Призёр регионального этапа", level: "region", place: 2, of: 40, year: 2025 }],
        match: { score: 0.94, explanation: [1, 2, 3].map((i) => ({ kind: "plus", text: `факт ${i}` })) as never },
      }),
      "backend",
    );
    expect(r.confirmed).toBe(true);
    expect(r.match).toBe(94);
    expect(r.strength).toEqual({ value: 71, label: "сила 71 · ранг 0.80" });
    expect(r.fsp).toBe("Призёр регионального этапа: 2 из 40");
    expect(r.reasons).toHaveLength(3);
    expect(r.place).toBe("Москва · удалённо");
  });

  it("toRankedCard: нет теста — предупреждение первым и пометка «грейд заявлен»", () => {
    const r = toRankedCard(card({ categories: [], match: { score: 0.5, explanation: [{ kind: "plus", text: "Вилка в бюджете" }] as never } }), "backend");
    expect(r.confirmed).toBe(false);
    expect(r.note).toBe("грейд заявлен");
    expect(r.reasons[0]).toEqual({ text: "Навыки не подтверждены тестом", warn: true });
  });
});
