import type { CandidateCard, FilterChip } from "@/api/model";
import { chipActive, chipApprox, chipText, EMPTY_FORM, fromParsed, gradeRange, removeChip, toCardData, toFilters } from "./search-model";

const chip = (key: string, value: unknown, label = "x", confidence = 0.9): FilterChip => ({ key, value, label, source: "rule", confidence });

test("диапазон грейдов: края включительно, пустой край открыт", () => {
  expect(gradeRange("junior_plus", "middle_plus")).toEqual(["junior_plus", "middle", "middle_plus"]);
  expect(gradeRange("senior", null)).toEqual(["senior", "lead"]);
  expect(gradeRange(null, null)).toEqual([]);
  expect(gradeRange("senior", "junior")).toEqual([]);
});

test("форма → фильтры: грейды сводятся к min/max, пустое не отправляем", () => {
  expect(toFilters(EMPTY_FORM)).toEqual({});
  const f = { ...EMPTY_FORM, grades: ["middle", "junior_plus"], minTrust: 3, salaryMax: 220000, semantic: "  api " };
  expect(toFilters(f)).toEqual({ grade_min: "junior_plus", grade_max: "middle", min_trust: 3, salary_max: 220000, semantic_text: "api" });
});

test("разбор → форма → фильтры сохраняет условия", () => {
  const filters = {
    roles: ["backend"],
    grade_min: "middle",
    grade_max: "senior",
    skills_must: [{ slug: "python" }],
    skills_nice: ["kafka"],
    formats: ["remote"],
    salary_max: 250000,
    fsp_only: true,
    cities: ["Казань"],
  };
  const form = fromParsed(filters as never, "trust");
  expect(form.sort).toBe("trust");
  expect(toFilters(form)).toEqual(filters);
});

test("крестик на чипсе убирает только своё условие", () => {
  const form = fromParsed(
    { roles: ["backend"], skills_must: [{ slug: "python" }, { slug: "go" }], grade_min: "middle", grade_max: "senior", salary_max: 200000 } as never,
    "match",
  );
  const py = chip("skills_must", { slug: "python" });
  expect(chipActive(py, form)).toBe(true);
  const next = removeChip(py, form);
  expect(next.skills).toEqual(["go"]);
  expect(chipActive(py, next)).toBe(false);
  expect(removeChip(chip("grade_max", "senior"), form).grades).toEqual(["middle", "middle_plus"]);
  expect(removeChip(chip("salary_max", 200000), form).salaryMax).toBeNull();
  expect(chipActive(chip("salary_max", 200000), { ...form, salaryMax: 300000 })).toBe(false);
});

test("подпись и «~» чипса", () => {
  expect(chipText(chip("skills_must", { slug: "python" }, "Навык: Python"))).toBe("Python");
  expect(chipApprox(chip("semantic_text", "api", "Смысл: api", 0.5))).toBe(true);
  expect(chipApprox(chip("formats", "remote", "Формат: Удалённо", 0.9))).toBe(false);
  expect(chipApprox({ ...chip("roles", "ml"), source: "llm" })).toBe(true);
});

test("карточка API → CandidateCard: псевдоним, навыки, ФСП, «почему»", () => {
  const card: CandidateCard = {
    pseudo_id: "p1",
    pseudonym: "Backend #4821",
    avatar_seed: "s",
    primary_role: "backend",
    grade: "junior_plus",
    grade_preliminary: true,
    primary_stack: ["python"],
    top_skills: [
      { slug: "python", name: "Python", level: 3, sources: ["github"] },
      { slug: "redis", name: "Redis", level: 0, sources: ["resume"] },
    ],
    fsp_highlights: [
      { title: "Продуктовое программирование", level: "national", place: 2, of: 40, year: 2025 },
      { title: "Без места", level: "regional", place: null, year: 2024 },
    ],
    salary_min: 150000,
    formats: ["remote", "hybrid"],
    city: null,
    relocation: false,
    search_status: "active",
    match: {
      score: 0.924,
      explanation: [
        { kind: "plus", code: "skill_confirmed" as never, text: "FastAPI подтверждён", weight: 1 },
        { kind: "minus", code: "skill_missing" as never, text: "Нет Kafka", weight: 1 },
      ],
    },
    updated_at: "2026-10-01T00:00:00Z",
  };
  const d = toCardData(card);
  expect(d).toMatchObject({ role: "Backend", number: "4821", grade: "Junior+", stack: "Python", gradePreliminary: true, match: 92 });
  expect(d.skills).toEqual([
    { name: "Python", level: 3, variant: "verified" },
    { name: "Redis", level: 0, variant: "claimed" },
  ]);
  expect(d.fsp).toEqual([{ discipline: "Продуктовое программирование", tournament: "", stage: "всероссийский этап", place: 2, total: 40, year: 2025 }]);
  expect(d.expectations?.[0]).toMatch(/^от 150/);
  expect(d.expectations?.[1]).toBe("Удалённо или гибрид");
  expect(d.why).toEqual([
    { kind: "ok", text: "FastAPI подтверждён" },
    { kind: "no", text: "Нет Kafka" },
  ]);
});
