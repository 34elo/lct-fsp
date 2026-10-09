import type { SkillWithTrust } from "@/api/model";

import { NO_FILTER, filterSkills, isFiltered, skillTypes, toggleHidden } from "./skills-model";

const sk = (slug: string, level: number, extra: Partial<SkillWithTrust> = {}, type: string | null = "hard"): SkillWithTrust => ({
  skill: { slug, name: slug.toUpperCase(), group: "language", type },
  confidence: level / 4,
  level,
  sources: ["test"],
  claimed_only: false,
  status: "active",
  derived_from: null,
  top_evidence: [],
  ...extra,
});

const skills = [sk("python", 4), sk("sql", 2, {}, "fundamental"), sk("redis", 0, { claimed_only: true }, null), sk("kafka", 1)];

describe("фильтр навыков профиля (E39-15)", () => {
  it("тип, доверие, статус, скрытые", () => {
    const slugs = (f = {}, hidden: string[] = []) => filterSkills(skills, new Set(hidden), { ...NO_FILTER, ...f }).map((s) => s.skill.slug);
    expect(slugs()).toEqual(["python", "sql", "kafka", "redis"]); // подтверждённые выше заявленных
    expect(slugs({ type: "fundamental" })).toEqual(["sql"]);
    expect(slugs({ trust: 2 })).toEqual(["python", "sql"]);
    expect(slugs({ state: "claimed" })).toEqual(["redis"]);
    expect(slugs({ state: "confirmed", q: "KA" })).toEqual(["kafka"]);
    expect(slugs({}, ["python"])).toEqual(["sql", "kafka", "redis"]);
    expect(slugs({ showHidden: true }, ["python"])).toEqual(["python", "sql", "kafka", "redis"]);
  });

  it("варианты типа, признак фильтра, переключение скрытия", () => {
    expect(skillTypes(skills)).toEqual(["fundamental", "hard"]);
    expect(isFiltered(NO_FILTER)).toBe(false);
    expect(isFiltered({ ...NO_FILTER, showHidden: true })).toBe(false);
    expect(isFiltered({ ...NO_FILTER, trust: 1 })).toBe(true);
    expect(toggleHidden(["sql"], "python")).toEqual(["python", "sql"]);
    expect(toggleHidden(["python", "sql"], "python")).toEqual(["sql"]);
  });
});
