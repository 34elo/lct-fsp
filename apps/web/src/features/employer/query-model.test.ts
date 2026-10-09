import { EMPTY_CRITERIA, criteriaKey, criteriaParams, filterCount, fromFilters, gradeSpan, hasSubject, mergeFilters, parseCriteria, toNeedFilters } from "./query-model";

test("условия ↔ URL: туда и обратно без потерь, мусор отбрасывается", () => {
  const c = {
    ...EMPTY_CRITERIA,
    skills: ["python", "django"],
    profession: "backend",
    grades: ["middle" as const],
    trust: 2,
    fsp: true,
    confirmed: true,
    cities: ["Москва"],
    salaryFrom: 150000,
    salaryTo: 250000,
    relocation: true,
    formats: ["remote"],
  };
  const p = criteriaParams(c, { need: "n1", cat: null });
  expect(p.get("need")).toBe("n1");
  expect(p.has("cat")).toBe(false);
  expect(parseCriteria(p)).toEqual(c);
  const junk = parseCriteria(new URLSearchParams("trust=9&grade=god&format=moon&from=-5&to=abc&skill=&skill=go&skill=go"));
  expect(junk).toEqual({ ...EMPTY_CRITERIA, skills: ["go"] });
  expect(criteriaKey(EMPTY_CRITERIA)).toBe("");
});

test("грейды — сплошным диапазоном", () => {
  expect(gradeSpan(["senior", "junior"])).toEqual(["junior", "middle", "senior"]);
  expect(gradeSpan(["middle"])).toEqual(["middle"]);
  expect(gradeSpan(["x"])).toEqual([]);
});

test("условия → фильтры потребности", () => {
  expect(toNeedFilters(EMPTY_CRITERIA)).toEqual({});
  const f = toNeedFilters({ ...EMPTY_CRITERIA, skills: ["python"], profession: "ai_engineer", grades: ["junior", "middle"], trust: 3, fsp: true, confirmed: true, salaryFrom: 100, salaryTo: 200, relocation: true, cities: ["Казань"], formats: ["office"] });
  expect(f).toEqual({
    skills_must: [{ slug: "python" }],
    professions: ["ai_engineer"],
    grade_min: "junior",
    grade_max: "middle",
    min_trust: 3,
    fsp_only: true,
    only_confirmed: true,
    salary_min: 100,
    salary_max: 200,
    relocation_ok: true,
    cities: ["Казань"],
    formats: ["office"],
  });
  expect(hasSubject(EMPTY_CRITERIA)).toBe(false);
  expect(hasSubject({ ...EMPTY_CRITERIA, profession: "qa" })).toBe(true);
  expect(filterCount({ ...EMPTY_CRITERIA, skills: ["x"], grades: ["middle"], salaryTo: 1 })).toBe(2);
});

test("разобранная фраза дополняет условия: «python django middle»", () => {
  const before = { ...EMPTY_CRITERIA, skills: ["sql"], fsp: true };
  const after = mergeFilters(before, { skills_must: [{ slug: "python" }, { slug: "django" }], grade_min: "middle", grade_max: "middle", roles: ["backend"] });
  expect(after.skills).toEqual(["sql", "python", "django"]);
  expect(after.profession).toBe("backend");
  expect(after.grades).toEqual(["middle"]);
  expect(after.fsp).toBe(true);
  // грейды резюме сворачиваются в тестовые; «senior+» — до senior
  expect(fromFilters({ grade_min: "middle_plus", grade_max: "lead" }).grades).toEqual(["middle", "senior"]);
  expect(fromFilters({ grade_min: "senior" }).grades).toEqual(["senior"]);
});
