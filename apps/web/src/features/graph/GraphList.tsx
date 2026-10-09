import { Link } from "react-router-dom";

import type { Node, Subgraph } from "@/api/model";
import { buildModel, pct, slugOf } from "@/features/graph/layout";
import { NODE_TYPE_LABEL, T } from "@/features/graph/text";

/** Тот же граф списком: для клавиатуры и скринридеров (схема `EvidenceGraph` из @fsp/ui — мышью и пальцем). */
export function GraphList({ graph }: { graph: Subgraph }) {
  const m = buildModel(graph);
  const byId = new Map<string, Node>(graph.nodes.map((n) => [n.id, n]));
  const label = (id: string) => byId.get(id)?.label ?? id;
  return (
    <section aria-label={T.listTitle} data-testid="graph-list" className="flex flex-col gap-4">
      <h2 className="font-mono text-lg font-semibold">{T.listTitle}</h2>
      <ul className="flex flex-col">
        {m.skills.map(({ node }) => {
          const proofs = m.confirms.filter((e) => e.to === node.id);
          const parents = m.relations.filter((e) => e.type === "parent" && e.from === node.id).map((e) => label(e.to));
          const adjacent = m.relations.filter((e) => e.type === "adjacent" && (e.from === node.id || e.to === node.id)).map((e) => label(e.from === node.id ? e.to : e.from));
          const hot = m.highlightedSkills.has(node.id);
          return (
            <li key={node.id} data-testid={`graph-skill-${slugOf(node.id)}`} className="flex flex-col gap-1 border-t border-hairline py-3 first:border-t-0">
              <span className="flex flex-wrap items-baseline gap-x-3">
                <span className="font-semibold">{node.label}</span>
                {node.ghost ? (
                  <span className="text-[13px] text-muted">
                    {T.ghost} ({T.ghostHint})
                  </span>
                ) : (
                  <span className="font-mono text-[13px] text-muted">
                    {T.level} {node.level ?? 0} · {T.confidence} {pct(node.confidence)}
                  </span>
                )}
                {hot && <span className="text-[13px] text-success">{T.highlighted}</span>}
              </span>
              {!node.ghost && proofs.length === 0 && <span className="text-[13px] text-muted">{T.claimedOnly}</span>}
              {proofs.length > 0 && (
                <div className="text-[13px] text-muted">
                  {T.confirmedBy}
                  <ul className="mt-1 flex flex-col gap-0.5">
                    {proofs.map((e, i) => {
                      const f = byId.get(e.from);
                      return (
                        <li key={i} className="flex flex-wrap gap-x-2">
                          <span className="text-ink">{f?.label ?? e.from}</span>
                          {f?.date && <span>{f.date}</span>}
                          {f && <span>{f.verified ? T.verified : T.notVerified}</span>}
                          <span className="font-mono">
                            {T.strength} {pct(e.strength)}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              {parents.length > 0 && (
                <span className="text-[13px] text-muted">
                  {T.partOf} {parents.join(", ")}
                </span>
              )}
              {adjacent.length > 0 && (
                <span className="text-[13px] text-muted">
                  {T.adjacent} {adjacent.join(", ")}
                </span>
              )}
              {!node.ghost && (
                <Link to={`/me/skills/${slugOf(node.id)}`} className="inline-flex min-h-11 items-center text-[13px] font-semibold text-brand-fg" aria-label={`${node.label}: ${T.skillLink}`}>
                  {T.skillLink}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
      {m.facts.length > 0 && (
        <>
          <h3 className="font-mono text-base font-semibold">{T.factsTitle}</h3>
          <ul className="flex flex-col gap-2 text-[13px]">
            {m.facts.map(({ node }) => (
              <li key={node.id} data-testid={`graph-fact-${node.id}`} className="flex flex-wrap gap-x-2">
                <span className="text-ink">{node.label}</span>
                <span className="text-muted">{NODE_TYPE_LABEL[node.type] ?? node.type}</span>
                {node.date && <span className="text-muted">{node.date}</span>}
                {node.verified != null && <span className="text-muted">{node.verified ? T.verified : T.notVerified}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
