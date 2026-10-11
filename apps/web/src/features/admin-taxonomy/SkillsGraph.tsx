import { useMemo } from "react";

import { Button, EmptyState, ErrorState, EvidenceGraph, Panel, Skeleton } from "@fsp/ui";

import {
  useGetGraphAdminSkillsGraphGet,
  useGetQueueAdminSkillsQueueGet,
  useListProvisionalAdminSkillsProvisionalGet,
} from "@/api/endpoints/admin/admin";
import { SK } from "./text";

type Target = "queue" | "provisional";

/** Вкладка «Карта связей»: граф справочника для просмотра и что ждёт решения. */
export function GraphTab({ onOpen }: { onOpen: (t: Target) => void }) {
  const g = useGetGraphAdminSkillsGraphGet({ query: { retry: false } });
  const queue = useGetQueueAdminSkillsQueueGet({ query: { retry: false } });
  const prov = useListProvisionalAdminSkillsProvisionalGet({ query: { retry: false } });
  const graph = g.data?.status === 200 ? g.data.data : null;
  const data = useMemo(
    () => (graph ? { nodes: graph.nodes.map((n) => ({ id: n.id, type: n.type ?? "skill", label: n.label, skill_type: n.skill_type })), edges: graph.edges.map((e) => ({ from: e.from, to: e.to, type: e.type, weight: e.weight })) } : null),
    [graph],
  );
  const q = queue.data?.status === 200 ? queue.data.data.length : 0;
  const p = prov.data?.status === 200 ? prov.data.data.length : 0;
  return (
    <div className="flex flex-col gap-4" data-testid="admin-sk-graph">
      <p className="text-14 text-muted">{SK.graph.lead}</p>
      {graph && (
        <div className="flex flex-wrap items-center gap-2 text-14" data-testid="admin-sk-graph-pending">
          {q + p === 0 ? (
            <span className="text-muted">{SK.graph.allClear}</span>
          ) : (
            <>
              <span className="font-semibold">{SK.graph.pending(q, p)}</span>
              {q > 0 && <Button type="button" size="sm" variant="outline" data-testid="admin-sk-graph-to-queue" onClick={() => onOpen("queue")}>{SK.graph.toQueue}</Button>}
              {p > 0 && <Button type="button" size="sm" variant="outline" data-testid="admin-sk-graph-to-new" onClick={() => onOpen("provisional")}>{SK.graph.toNew}</Button>}
            </>
          )}
        </div>
      )}
      {g.isLoading && <Skeleton className="h-64" />}
      {(g.isError || (g.data && g.data.status !== 200)) && <ErrorState description={SK.loadError} onRetry={() => void g.refetch()} />}
      {graph && graph.nodes.length === 0 && <EmptyState title={SK.graph.empty} description={SK.graph.emptyText} />}
      {graph && data && graph.nodes.length > 0 && (
        <>
          <p className="text-13 text-muted" data-testid="admin-sk-graph-summary">{SK.graph.summary(graph.nodes.length, graph.edges.length, graph.version)}</p>
          <Panel className="p-4 md:p-5">
            <EvidenceGraph data={data} title={null} info={null} hideConfirmedFilter data-testid="admin-sk-egraph" />
          </Panel>
        </>
      )}
    </div>
  );
}
