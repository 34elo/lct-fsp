import type { Edge, Node, Subgraph } from "@/api/model";

/** Модель списка графа (GraphList): факты, навыки, рёбра и подсветка путей вакансии. Схему рисует `EvidenceGraph` из @fsp/ui. */
export type GraphModel = {
  facts: { node: Node }[];
  skills: { node: Node }[];
  confirms: Edge[];
  relations: Edge[];
  /** Рёбра подсвеченных путей в виде «a|b» (в обе стороны). */
  highlightedPairs: Set<string>;
  highlightedSkills: Set<string>;
};

export const isSkill = (n: Node) => n.type === "skill";
export const slugOf = (id: string) => (id.startsWith("s:") ? id.slice(2) : id);
export const pairKey = (a: string, b: string) => `${a}|${b}`;

/** Чистая функция: порядок узлов сохраняется как в ответе API. */
export function buildModel(g: Subgraph): GraphModel {
  const facts = g.nodes.filter((n) => n.type !== "candidate" && !isSkill(n));
  const skills = g.nodes.filter(isSkill);
  const ids = new Set(g.nodes.map((n) => n.id));
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
  return { facts: facts.map((node) => ({ node })), skills: skills.map((node) => ({ node })), confirms, relations, highlightedPairs, highlightedSkills };
}

export const pct = (v?: number | null) => `${Math.round((v ?? 0) * 100)}%`;
