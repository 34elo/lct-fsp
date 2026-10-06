import type { Edge, Node, Subgraph } from "@/api/model";

/** Размеры схемы (viewBox). Факты слева, навыки справа; дуги parent/adjacent — правее колонки навыков. */
export const VB_WIDTH = 760;
export const NODE_H = 44;
export const ROW = 56;
export const FACT_X = 0;
export const FACT_W = 280;
export const SKILL_X = 440;
export const SKILL_W = 250;

export type Placed = { node: Node; x: number; y: number; w: number };

export type GraphModel = {
  facts: Placed[];
  skills: Placed[];
  confirms: Edge[];
  relations: Edge[];
  height: number;
  /** Рёбра подсвеченных путей в виде «a|b» (в обе стороны). */
  highlightedPairs: Set<string>;
  highlightedSkills: Set<string>;
};

export const isSkill = (n: Node) => n.type === "skill";
export const slugOf = (id: string) => (id.startsWith("s:") ? id.slice(2) : id);
export const pairKey = (a: string, b: string) => `${a}|${b}`;

/** Чистая раскладка: никаких зависимостей, порядок узлов сохраняется как в ответе API. */
export function buildModel(g: Subgraph): GraphModel {
  const facts = g.nodes.filter((n) => n.type !== "candidate" && !isSkill(n));
  const skills = g.nodes.filter(isSkill);
  const ids = new Set(g.nodes.map((n) => n.id));
  const rows = Math.max(facts.length, skills.length, 1);
  const place = (list: Node[], x: number, w: number): Placed[] =>
    list.map((node, i) => ({ node, x, w, y: i * ROW + 4 }));
  const confirms = g.edges.filter((e) => (e.type === "confirms" || e.type === "owns") && ids.has(e.from) && ids.has(e.to));
  const relations = g.edges.filter((e) => (e.type === "parent" || e.type === "adjacent") && ids.has(e.from) && ids.has(e.to));
  const highlightedPairs = new Set<string>();
  const highlightedSkills = new Set<string>();
  for (const h of g.highlight ?? []) {
    h.path.forEach((id, i) => {
      if (id.startsWith("s:")) highlightedSkills.add(id);
      const next = h.path[i + 1];
      if (next) {
        highlightedPairs.add(pairKey(id, next));
        highlightedPairs.add(pairKey(next, id));
      }
    });
  }
  return {
    facts: place(facts, FACT_X, FACT_W),
    skills: place(skills, SKILL_X, SKILL_W),
    confirms,
    relations,
    height: rows * ROW + 8,
    highlightedPairs,
    highlightedSkills,
  };
}

export const pct = (v?: number | null) => `${Math.round((v ?? 0) * 100)}%`;
export const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
