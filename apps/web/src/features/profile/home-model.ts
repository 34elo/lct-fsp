/** Чистые функции Главной кандидата (E38-1): следующий шаг, созвездие, строки навыков, форматы. */
import type { OfferForCandidate } from "@/api/model";
import type { CircuitStep, ConstellationNode } from "@fsp/ui";

import { FORMAT_WORD, HOME, SOURCE_TAG } from "./text";

export type StepKey = "test" | "fsp" | "interest" | "next";

export interface NextStepInput {
  /** Есть действующий грейд по тесту (`/candidates/me/standing`). */
  tested: boolean;
  /** Профиль ФСП привязан. */
  fspLinked: boolean;
  /** Интересы работодателей без ответа кандидата. */
  pendingInterests: number;
  /** Следующий тест из навигатора: грейд (подпись) и маршрут. */
  nextTest?: { grade: string; path: string } | null;
}

export interface NextStep {
  steps: CircuitStep[];
  /** Текущий шаг и его единственное действие; `null` — всё пройдено. */
  current: { key: StepKey; label: string; to: string } | null;
}

/**
 * «Следующий шаг» (бриф §6.1): тест → ФСП → ответ на интерес → тест на следующий грейд.
 * Шаг «интерес» есть, только пока есть интересы без ответа; «тест на грейд» — пока навигатор его предлагает.
 * Текущий — первый не пройденный, дальше — будущие.
 */
export function nextStep(i: NextStepInput): NextStep {
  const raw: { key: StepKey; done: boolean; label: string; action: string; to: string }[] = [
    { key: "test", done: i.tested, label: i.tested ? HOME.steps.test.done : HOME.steps.test.todo, action: HOME.steps.test.todo, to: "/me/assessment" },
    { key: "fsp", done: i.fspLinked, label: i.fspLinked ? HOME.steps.fsp.done : HOME.steps.fsp.todo, action: HOME.steps.fsp.todo, to: "/onboarding" },
  ];
  if (i.pendingInterests > 0)
    raw.push({ key: "interest", done: false, label: HOME.steps.interest.todo, action: HOME.steps.interest.todo, to: "/me/offers?show=interests" });
  if (i.nextTest)
    raw.push({ key: "next", done: false, label: HOME.nextTest(i.nextTest.grade), action: HOME.nextTestAction(i.nextTest.grade), to: i.nextTest.path });
  const cur = raw.findIndex((s) => !s.done);
  return {
    steps: raw.map((s, k) => ({ id: s.key, label: s.label, state: s.done ? "done" : k === cur ? "current" : "future" })),
    current: cur < 0 ? null : { key: raw[cur].key, label: raw[cur].action, to: raw[cur].to },
  };
}

interface SkillLike {
  skill: { slug: string; name: string };
  level: number;
  claimed_only: boolean;
  sources: string[];
}

const dots4 = (level: number) => Math.max(0, Math.min(4, Math.round(level)));

/** Подтверждённые выше заявленных, внутри — по силе. */
export function sortSkills<S extends SkillLike>(skills: S[]): S[] {
  return [...skills].sort((a, b) => Number(a.claimed_only) - Number(b.claimed_only) || b.level - a.level);
}

/**
 * Узлы созвездия: навыки профиля (подтверждено / заявлено) и смежные навыки из навигатора.
 * `claimedOnly` — до теста все навыки рисуются заявленными, к ним добавляется стек из опроса.
 */
export function constellationNodes(
  skills: SkillLike[],
  opts: { adjacent?: string[]; stack?: string[]; claimedOnly?: boolean } = {},
): ConstellationNode[] {
  const nodes: ConstellationNode[] = sortSkills(skills).map((s) => ({
    name: s.skill.name,
    level: opts.claimedOnly || s.claimed_only ? 0 : dots4(s.level),
    state: opts.claimedOnly || s.claimed_only ? "claimed" : "confirmed",
  }));
  const seen = new Set(nodes.map((n) => n.name.toLowerCase()));
  const add = (name: string, state: ConstellationNode["state"]) => {
    const key = name.trim().toLowerCase();
    if (!key || seen.has(key)) return;
    seen.add(key);
    nodes.push({ name: name.trim(), level: 0, state });
  };
  for (const s of opts.stack ?? []) add(s, "claimed");
  for (const a of (opts.adjacent ?? []).slice(0, 3)) add(a, "adjacent");
  return nodes;
}

/** Метка источника в строке навыка: заявленный — «заявлен», иначе самый сильный источник. */
export function skillSource(s: SkillLike): { text: string; claimed: boolean } {
  if (s.claimed_only) return { text: HOME.skillClaimed, claimed: true };
  const src = ["test", "fsp", "task", "resume"].find((k) => s.sources.includes(k)) ?? s.sources[0];
  return { text: (src && SOURCE_TAG[src]) ?? src ?? HOME.skillClaimed, claimed: !src };
}

/** «Удалёнка или гибрид». */
export function formatsText(formats: string[]): string {
  const words = formats.map((f) => FORMAT_WORD[f] ?? f);
  if (!words.length) return "";
  const s = words.length === 1 ? words[0] : `${words.slice(0, -1).join(", ")} или ${words[words.length - 1]}`;
  return s[0].toUpperCase() + s.slice(1);
}

/** Рейтинг ответственности компании «4.6 / 5»: API отдаёт 0–1 (джоб рейтингов) или уже 0–5. */
export function ratingText(score: number | null | undefined): string | undefined {
  if (score == null || !Number.isFinite(score)) return undefined;
  const v = score <= 1 ? score * 5 : score;
  return HOME.rating(v.toFixed(1));
}

/** «07.10» по ISO-дате (UTC). */
export function dayMonth(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", timeZone: "UTC" });
}

/** Последние приглашения и интересы одним списком (E39-13): статус, вилка, ссылка на карточку. */
export function latestInvites(interests: OfferForCandidate[], offers: OfferForCandidate[], n = 3): OfferForCandidate[] {
  const byId = new Map<string, OfferForCandidate>();
  for (const o of [...interests, ...offers]) if (o.initiator !== "candidate") byId.set(o.id, o);
  return [...byId.values()].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? "")).slice(0, n);
}
