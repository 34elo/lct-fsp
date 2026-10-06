import { useState } from "react";

import { Badge, Button, Card, CardContent, EmptyState, ErrorState, Skeleton } from "@fsp/ui";

import {
  useApproveQueueAdminSkillsQueueSlugApprovePost,
  useGetQueueAdminSkillsQueueGet,
  useListMergesAdminSkillsMergesGet,
  useRejectQueueAdminSkillsQueueSlugRejectPost,
  useRevertMergeAdminSkillsMergesMergeIdRevertPost,
} from "@/api/endpoints/admin/admin";
import type { QueueItem } from "@/api/model";
import { Notice, shortDate, skErr, useRefreshSkills } from "./SkillsShared";
import { SK } from "./text";

const sel = (s: string) => `admin-sk-${s}`;

function QueueCard({ item, onDone }: { item: QueueItem; onDone: (ok: string, err: string | null) => void }) {
  const refresh = useRefreshSkills();
  const [distinct, setDistinct] = useState(false);
  const done = (ok: string) => { void refresh(); onDone(ok, null); };
  const approve = useApproveQueueAdminSkillsQueueSlugApprovePost({ mutation: { onSuccess: () => done(SK.queue.merged(item.skill_name, item.into_name)), onError: (e) => onDone("", skErr(e)) } });
  const reject = useRejectQueueAdminSkillsQueueSlugRejectPost({ mutation: { onSuccess: () => done(SK.queue.rejected), onError: (e) => onDone("", skErr(e)) } });
  const busy = approve.isPending || reject.isPending;
  const pct = item.confidence == null ? null : Math.round(item.confidence * 100);
  return (
    <Card data-testid={sel(`queue-item-${item.skill}`)}>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex flex-wrap items-center gap-2 text-14">
          <span className="font-semibold">{item.skill_name}</span>
          <Badge variant="muted">{item.from.status === "provisional" ? SK.queue.newBadge : item.from.status}</Badge>
          <span className="text-muted">{SK.queue.into}</span>
          <span className="font-semibold">{item.into_name}</span>
          {pct !== null && <Badge data-testid={sel(`confidence-${item.skill}`)}>{SK.queue.confidence(pct)}</Badge>}
        </div>
        <p className="text-13 text-muted">{SK.queue.mention}: «{item.norm}»</p>
        <div className="rounded-lg border border-hairline p-3 text-13" data-testid={sel(`preview-${item.skill}`)}>
          <p className="font-semibold">{SK.queue.preview}</p>
          <p>{SK.queue.aliases}: {item.preview.aliases.join(", ")}</p>
          <p>{SK.queue.relations(item.preview.relations)}</p>
          <p>{SK.queue.support(item.preview.support_candidates, item.preview.support_vacancies)}</p>
        </div>
        <label className="flex items-center gap-2 text-13">
          <input type="checkbox" data-testid={sel(`distinct-check-${item.skill}`)} checked={distinct} onChange={(e) => setDistinct(e.target.checked)} />
          {SK.queue.markDistinct}
        </label>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={busy} data-testid={sel(`merge-${item.skill}`)} onClick={() => approve.mutate({ slug: item.skill })}>{SK.queue.merge}</Button>
          <Button type="button" variant="outline" disabled={busy} data-testid={sel(`reject-${item.skill}`)} onClick={() => reject.mutate({ slug: item.skill, data: { mark_distinct: distinct } })}>{SK.queue.reject}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function QueueTab() {
  const q = useGetQueueAdminSkillsQueueGet({ query: { retry: false } });
  const [ok, setOk] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const items = q.data?.status === 200 ? q.data.data : null;
  return (
    <div className="flex flex-col gap-3" data-testid={sel("queue")}>
      <Notice ok={ok} err={err} />
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={SK.loadError} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={SK.queue.empty} description={SK.queue.emptyText} />}
      {items?.map((i) => <QueueCard key={i.skill} item={i} onDone={(o, e) => { setOk(o); setErr(e); }} />)}
    </div>
  );
}

export function MergesTab() {
  const q = useListMergesAdminSkillsMergesGet({ query: { retry: false } });
  const refresh = useRefreshSkills();
  const [ok, setOk] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);
  const revert = useRevertMergeAdminSkillsMergesMergeIdRevertPost({
    mutation: {
      onSuccess: () => { void refresh(); setConfirm(null); setErr(null); setOk(SK.merges.reverted); },
      onError: (e) => { setConfirm(null); setOk(""); setErr(skErr(e)); },
    },
  });
  const items = q.data?.status === 200 ? q.data.data : null;
  return (
    <div className="flex flex-col gap-3" data-testid={sel("merges")}>
      <Notice ok={ok} err={err} />
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={SK.loadError} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={SK.merges.empty} description={SK.merges.emptyText} />}
      {items && items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((m) => (
            <li key={m.id} data-testid={sel(`merge-row-${m.from_skill}`)}>
              <Card>
                <CardContent className="flex flex-col gap-2 py-3">
                  <div className="flex flex-wrap items-center gap-2 text-14">
                    <span className="font-semibold">{m.from_name}</span>
                    <span className="text-muted">→</span>
                    <span className="font-semibold">{m.into_name}</span>
                    {m.reverted_at && <Badge variant="muted">{SK.merges.revertedBadge}</Badge>}
                  </div>
                  <p className="text-13 text-muted">
                    {shortDate(m.created_at)} · {SK.merges.actor(m.actor)} · {SK.merges.moved(m.aliases_added, m.rows_moved)}
                  </p>
                  {!m.reverted_at && confirm !== m.id && (
                    <div>
                      <Button type="button" size="sm" variant="outline" data-testid={sel(`revert-${m.from_skill}`)} onClick={() => setConfirm(m.id)}>{SK.merges.revert}</Button>
                    </div>
                  )}
                  {confirm === m.id && (
                    <div className="flex flex-wrap items-center gap-2" data-testid={sel(`revert-confirm-${m.from_skill}`)}>
                      <span className="text-13">{SK.merges.revertConfirm(m.from_name, m.into_name)}</span>
                      <Button type="button" size="sm" disabled={revert.isPending} data-testid={sel(`revert-yes-${m.from_skill}`)} onClick={() => revert.mutate({ mergeId: m.id })}>{SK.merges.revertYes}</Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
