import type { ExperienceBrief, FspHighlight, SkillWithTrust } from "@/api/model";
import type { FspResult, TrustKind, TrustSource } from "@fsp/ui";
import { dots } from "@/features/profile/text";
import { FSP_LEVEL_LABEL, SOURCE_SHORT } from "./text";

/** Группы навыков для экрана B (slug группы из ядра навыков → подпись). */
export const SKILL_GROUP_LABEL: Record<string, string> = {
  language: "Языки и алгоритмы",
  algorithms: "Алгоритмы",
  backend: "Бэкенд и API",
  frontend: "Фронтенд",
  mobile: "Мобильная разработка",
  db: "Данные и очереди",
  data: "Данные и ML",
  ml: "Данные и ML",
  devops: "Инфраструктура",
  infra: "Инфраструктура",
  testing: "Качество и тесты",
  analysis: "Анализ и документация",
  tools: "Инструменты",
};

const OTHER_GROUP = "Другое";

export function groupLabel(group: string | undefined): string {
  return (group && SKILL_GROUP_LABEL[group]) || (group ? group.charAt(0).toUpperCase() + group.slice(1) : OTHER_GROUP);
}

export function kindOf(s: SkillWithTrust): TrustKind {
  if (s.claimed_only) return "claimed";
  if (s.derived_from) return "inferred";
  if (s.status === "provisional") return "provisional";
  return "verified";
}

/** Навык с одним slug показываем один раз: берём сильнейшую запись, источники и доказательства объединяем. */
export function dedupeSkills(skills: SkillWithTrust[]): SkillWithTrust[] {
  const by = new Map<string, SkillWithTrust>();
  for (const s of skills) {
    const prev = by.get(s.skill.slug);
    if (!prev) {
      by.set(s.skill.slug, { ...s, sources: [...new Set(s.sources)], top_evidence: dedupeBy(s.top_evidence, (e) => e.id) });
      continue;
    }
    const strong = s.level > prev.level || (s.level === prev.level && prev.claimed_only && !s.claimed_only) ? s : prev;
    by.set(s.skill.slug, {
      ...strong,
      claimed_only: prev.claimed_only && s.claimed_only,
      sources: [...new Set([...prev.sources, ...s.sources])],
      top_evidence: dedupeBy([...prev.top_evidence, ...s.top_evidence], (e) => e.id),
    });
  }
  return [...by.values()];
}

function dedupeBy<T>(items: T[], key: (t: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter((i) => {
    const k = key(i);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

export interface SkillGroup {
  label: string;
  skills: SkillWithTrust[];
}

export interface GroupedSkills {
  /** Подтверждённые и выведенные: по группам, сильные первыми. */
  groups: SkillGroup[];
  /** Только из резюме: свёрнуты в одну строку. */
  claimed: SkillWithTrust[];
}

export function groupSkills(all: SkillWithTrust[]): GroupedSkills {
  const skills = dedupeSkills(all);
  const claimed = skills.filter((s) => s.claimed_only);
  const rest = skills.filter((s) => !s.claimed_only);
  const map = new Map<string, SkillWithTrust[]>();
  for (const s of rest) {
    const label = groupLabel(s.skill.group);
    map.set(label, [...(map.get(label) ?? []), s]);
  }
  const groups = [...map.entries()]
    .map(([label, list]) => ({ label, skills: [...list].sort((a, b) => b.level - a.level || a.skill.name.localeCompare(b.skill.name)) }))
    .sort((a, b) => b.skills.length - a.skills.length || a.label.localeCompare(b.label));
  return { groups, claimed };
}

/** Источники для поповера «Откуда навык»: доказательства, а не текст под каждым навыком. */
export function trustSources(s: SkillWithTrust): TrustSource[] {
  if (s.top_evidence.length === 0) {
    return s.sources.map((x) => ({ title: SOURCE_SHORT[x] ?? x, strength: "none" as const }));
  }
  return s.top_evidence.map((e) => ({
    title: e.title,
    detail: `${SOURCE_SHORT[e.source] ?? e.source}${e.verified ? ", проверено" : ""}`,
    strength: e.strength >= 0.7 ? "strong" : e.strength >= 0.4 ? "medium" : "weak",
    date: new Date(e.observed_at).toLocaleDateString("ru-RU", { month: "short", year: "numeric", timeZone: "UTC" }),
  }));
}

export function skillLevel(s: SkillWithTrust): 0 | 1 | 2 | 3 | 4 {
  return dots(s.level);
}

export function fspResults(list: FspHighlight[]): FspResult[] {
  const uniq = dedupeBy(list, (h) => `${h.title}|${h.level}|${h.place ?? ""}|${h.of ?? ""}|${h.year}`);
  return uniq.map((h) => ({
    discipline: h.title,
    tournament: FSP_LEVEL_LABEL[h.level] ?? h.level,
    place: h.place ?? 0,
    total: h.of ?? undefined,
    year: h.year,
    note: h.note ?? undefined,
  }));
}

export function dedupeExperience(list: ExperienceBrief[]): ExperienceBrief[] {
  return dedupeBy(list, (e) => `${e.title}|${e.company ?? ""}|${e.months}`);
}

/** Радар: максимальный уровень навыка (0–4) по группам. */
export function radarAxes(groups: SkillGroup[]): { label: string; value: number }[] {
  return groups.slice(0, 6).map((g) => ({ label: g.label, value: Math.max(...g.skills.map((s) => skillLevel(s))) }));
}


export function yearsLabel(months: number): string {
  const y = Math.floor(months / 12);
  const m = months % 12;
  return [y ? `${y} г` : "", m ? `${m} мес` : ""].filter(Boolean).join(" ") || "меньше месяца";
}
