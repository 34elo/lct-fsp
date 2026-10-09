import type { SkillWithTrust } from "@/api/model";
import { dedupeExperience, dedupeSkills, filterSkills, fspResults, groupSkills, radarAxes, rankSkills, splitClaimed, yearsLabel } from "./candidate-model";

const sk = (slug: string, group: string, level: number, claimed = false, ev: string[] = []): SkillWithTrust => ({
  skill: { slug, name: slug, group },
  confidence: 0.5,
  level,
  sources: [claimed ? "resume" : "fsp"],
  claimed_only: claimed,
  status: "active",
  top_evidence: ev.map((id) => ({ id, source: "fsp", strength: 0.9, observed_at: "2026-01-10", title: id, verified: true })),
});

test("навык с одним slug показывается один раз, источники и доказательства объединяются", () => {
  const r = dedupeSkills([sk("python", "language", 2, true), sk("python", "language", 3, false, ["e1"]), sk("python", "language", 3, false, ["e1", "e2"])]);
  expect(r).toHaveLength(1);
  expect(r[0].level).toBe(3);
  expect(r[0].claimed_only).toBe(false);
  expect(r[0].sources.sort()).toEqual(["fsp", "resume"]);
  expect(r[0].top_evidence.map((e) => e.id)).toEqual(["e1", "e2"]);
});

test("группы: подтверждённые по группам, заявленные отдельно", () => {
  const g = groupSkills([sk("python", "language", 3), sk("fastapi", "backend", 2), sk("redis", "db", 0, true), sk("go", "language", 4)]);
  expect(g.claimed.map((s) => s.skill.slug)).toEqual(["redis"]);
  expect(g.groups[0].label).toBe("Языки и алгоритмы");
  expect(g.groups[0].skills.map((s) => s.skill.slug)).toEqual(["go", "python"]);
  expect(radarAxes(g.groups)).toEqual([{ label: "Языки и алгоритмы", value: 4 }, { label: "Бэкенд и API", value: 2 }]);
});

test("повторы в ФСП и опыте убираются", () => {
  const h = { title: "Кубок", level: "national", place: 2, of: 40, year: 2025 };
  expect(fspResults([h, { ...h }])).toEqual([{ discipline: "Кубок", tournament: "всероссийский этап", place: 2, total: 40, year: 2025 }]);
  const e = { title: "Backend", company: null, months: 20, skills: [] };
  expect(dedupeExperience([e, { ...e }])).toHaveLength(1);
  expect(yearsLabel(20)).toBe("1 г 8 мес");
});

test("навыки: подтверждённые первыми, разбиение на колонки, поиск и фильтр", () => {
  const all = [sk("redis", "db", 0, true), sk("python", "language", 3), sk("go", "language", 4), sk("docker", "devops", 1, true)];
  expect(rankSkills(all).map((s) => s.skill.slug)).toEqual(["go", "python", "docker", "redis"]);
  const { confirmed, claimed } = splitClaimed(all);
  expect(confirmed).toHaveLength(2);
  expect(claimed).toHaveLength(2);
  const ranked = rankSkills(all);
  expect(filterSkills(ranked, "", "claimed").map((s) => s.skill.slug)).toEqual(["docker", "redis"]);
  expect(filterSkills(ranked, " PYT ", "all").map((s) => s.skill.slug)).toEqual(["python"]);
  expect(filterSkills(ranked, "py", "claimed")).toEqual([]);
});

test("ФСП: релевантные первыми и с подписью", () => {
  const base = { level: "national", place: 1, of: 10, year: 2025 };
  const r = fspResults([
    { ...base, title: "Другое", relevance: "other" },
    { ...base, title: "Бэкенд", relevance: "relevant" },
  ]);
  expect(r.map((x) => x.discipline)).toEqual(["Бэкенд", "Другое"]);
  expect(r[0].note).toBe("релевантно профессии");
  expect(r[1].note).toBe("соревнование другого направления");
});
