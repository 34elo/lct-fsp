import { Link } from "react-router-dom";

import type { Node, Subgraph } from "@/api/model";
import { buildModel, clip, NODE_H, pairKey, pct, SKILL_W, SKILL_X, slugOf, VB_WIDTH, type Placed } from "@/features/graph/layout";
import { NODE_TYPE_LABEL, T } from "@/features/graph/text";

function SvgNode({ p, ghost, hot }: { p: Placed; ghost?: boolean; hot?: boolean }) {
  const { node } = p;
  const sub = node.type === "skill" ? (ghost ? T.ghost : `${T.level} ${node.level ?? 0} · ${pct(node.confidence)}`) : `${NODE_TYPE_LABEL[node.type] ?? node.type}${node.date ? ` · ${node.date}` : ""}`;
  return (
    <g data-testid={`graph-node-${node.id}`} transform={`translate(${p.x} ${p.y})`}>
      <title>{node.label}</title>
      <rect
        width={p.w}
        height={NODE_H}
        rx={10}
        className={`fill-card ${hot ? "stroke-success" : node.verified ? "stroke-brand-fg" : "stroke-hairline"}`}
        strokeWidth={hot || node.verified ? 2 : 1}
        strokeDasharray={ghost ? "5 4" : undefined}
      />
      <text x={12} y={19} className={`text-[13px] font-semibold ${ghost ? "fill-muted" : "fill-ink"}`}>
        {clip(node.label, p.w > 260 ? 36 : 30)}
      </text>
      <text x={12} y={35} className="fill-muted font-mono text-[11px]">
        {clip(sub, 40)}
      </text>
    </g>
  );
}

/** Схема для широких экранов. Для клавиатуры и скринридеров та же информация есть в списке (GraphList). */
export function GraphSvg({ graph }: { graph: Subgraph }) {
  const m = buildModel(graph);
  const pos = new Map([...m.facts, ...m.skills].map((p) => [p.node.id, p]));
  return (
    <svg
      data-testid="graph-svg"
      role="img"
      aria-label={T.figureLabel}
      viewBox={`0 0 ${VB_WIDTH} ${m.height}`}
      className="w-full text-ink"
      style={{ fontFamily: "var(--font-sans)" }}
    >
      {m.confirms.map((e, i) => {
        const a = pos.get(e.from);
        const b = pos.get(e.to);
        if (!a || !b) return null;
        const x1 = a.x + a.w;
        const y1 = a.y + NODE_H / 2;
        const y2 = b.y + NODE_H / 2;
        const mx = (x1 + b.x) / 2;
        const hot = m.highlightedPairs.has(pairKey(e.from, e.to));
        return (
          <path
            key={`c${i}`}
            data-testid="graph-edge-confirms"
            d={`M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${b.x} ${y2}`}
            fill="none"
            className={hot ? "stroke-success" : e.type === "owns" ? "stroke-muted" : "stroke-brand-fg"}
            strokeOpacity={hot ? 1 : 0.7}
            strokeWidth={1 + (e.strength ?? 0.2) * 4}
            strokeDasharray={e.type === "owns" ? "2 4" : undefined}
          />
        );
      })}
      {m.relations.map((e, i) => {
        const a = pos.get(e.from);
        const b = pos.get(e.to);
        if (!a || !b) return null;
        const x = SKILL_X + SKILL_W;
        const y1 = a.y + NODE_H / 2;
        const y2 = b.y + NODE_H / 2;
        const bulge = x + 14 + Math.min(40, Math.abs(y2 - y1) / 6);
        return (
          <path
            key={`r${i}`}
            data-testid={`graph-edge-${e.type}`}
            d={`M${x} ${y1} Q${bulge} ${(y1 + y2) / 2} ${x} ${y2}`}
            fill="none"
            className="stroke-muted"
            strokeWidth={1.5}
            strokeDasharray={e.type === "adjacent" ? "6 4" : "1 4"}
          />
        );
      })}
      {m.facts.map((p) => (
        <SvgNode key={p.node.id} p={p} />
      ))}
      {m.skills.map((p) => (
        <SvgNode key={p.node.id} p={p} ghost={!!p.node.ghost} hot={m.highlightedSkills.has(p.node.id)} />
      ))}
    </svg>
  );
}

export function Legend() {
  return (
    <ul data-testid="graph-legend" className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted">
      <li>{T.legendSolid}</li>
      <li>{T.legendDashed}</li>
      <li>{T.legendDotted}</li>
    </ul>
  );
}

/** Доступная альтернатива схеме и единственный вид на 375 px. */
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

/** Граф целиком: схема на md+, список всегда. `graph` можно подать и с `highlight`/`ghost` (вариант работодателя). */
export default function EvidenceGraph({ graph }: { graph: Subgraph }) {
  return (
    <div data-testid="graph-root" className="flex flex-col gap-4">
      <div className="hidden flex-col gap-3 md:flex" data-testid="graph-figure">
        <GraphSvg graph={graph} />
        <Legend />
      </div>
      <GraphList graph={graph} />
    </div>
  );
}
