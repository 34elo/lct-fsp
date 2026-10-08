import { useState, type FormEvent } from "react";

import { Badge, Button, Card, CardContent, EmptyState, ErrorState, Skeleton, useFieldProps } from "@fsp/ui";

import {
  useAddBlocklistAdminSkillsBlocklistPost,
  useAddDistinctAdminSkillsDistinctPost,
  useApproveSkillAdminSkillsSlugApprovePost,
  useGetHintsAdminSkillsHintsGet,
  useListBlocklistAdminSkillsBlocklistGet,
  useListDistinctAdminSkillsDistinctGet,
  useListProvisionalAdminSkillsProvisionalGet,
  useRejectSkillAdminSkillsSlugRejectPost,
  useRemoveBlocklistAdminSkillsBlocklistDelete,
  useRemoveDistinctAdminSkillsDistinctDelete,
} from "@/api/endpoints/admin/admin";
import { fieldClass } from "@/features/auth/ui";
import { Notice, shortDate, skErr, useRefreshSkills } from "./SkillsShared";
import { SK } from "./text";

const sel = (s: string) => `admin-sk-${s}`;

function In(p: React.InputHTMLAttributes<HTMLInputElement>) {
  const fp = useFieldProps();
  return <input {...fp} className={fieldClass} {...p} />;
}

const Loading = ({ q }: { q: { isLoading: boolean; isError: boolean; data?: { status: number }; refetch: () => unknown } }) => (
  <>
    {q.isLoading && <Skeleton className="h-32" />}
    {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={SK.loadError} onRetry={() => void q.refetch()} />}
  </>
);

function useResult() {
  const refresh = useRefreshSkills();
  const [ok, setOk] = useState("");
  const [err, setErr] = useState<string | null>(null);
  return {
    ok, err,
    success: (m: string) => { void refresh(); setErr(null); setOk(m); },
    fail: (e: unknown) => { setOk(""); setErr(skErr(e)); },
    local: (m: string) => { setOk(""); setErr(m); },
  };
}

export function DistinctTab() {
  const q = useListDistinctAdminSkillsDistinctGet({ query: { retry: false } });
  const r = useResult();
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const add = useAddDistinctAdminSkillsDistinctPost({
    mutation: { onSuccess: (res) => { r.success(res.status === 200 && !res.data.changed ? SK.distinct.exists : SK.distinct.added); setA(""); setB(""); }, onError: r.fail },
  });
  const remove = useRemoveDistinctAdminSkillsDistinctDelete({ mutation: { onSuccess: () => r.success(SK.distinct.removed), onError: r.fail } });
  const items = q.data?.status === 200 ? q.data.data : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!a.trim() || !b.trim()) return r.local(SK.distinct.local);
    add.mutate({ data: { a: a.trim(), b: b.trim() } });
  };
  return (
    <div className="flex flex-col gap-3" data-testid={sel("distinct")}>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end" data-testid={sel("distinct-form")}>
        <label className="flex flex-1 flex-col gap-1 text-13">{SK.distinct.a}<In data-testid={sel("distinct-a")} value={a} onChange={(e) => setA(e.target.value)} /></label>
        <label className="flex flex-1 flex-col gap-1 text-13">{SK.distinct.b}<In data-testid={sel("distinct-b")} value={b} onChange={(e) => setB(e.target.value)} /></label>
        <Button type="submit" disabled={add.isPending} data-testid={sel("distinct-add")}>{SK.distinct.add}</Button>
      </form>
      <p className="text-12 text-muted">{SK.distinct.hint}</p>
      <Notice ok={r.ok} err={r.err} />
      <Loading q={q} />
      {items && items.length === 0 && <EmptyState title={SK.distinct.empty} description={SK.distinct.emptyText} />}
      {items && items.length > 0 && (
        <ul className="flex flex-col gap-2" data-testid={sel("distinct-list")}>
          {items.map((p) => (
            <li key={`${p.a}|${p.b}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline px-3 py-2" data-testid={sel(`distinct-row-${p.a}-${p.b}`)}>
              <span className="text-14"><span className="font-semibold">{p.a_name}</span> ≠ <span className="font-semibold">{p.b_name}</span></span>
              <Button type="button" size="sm" variant="ghost" disabled={remove.isPending} data-testid={sel(`distinct-remove-${p.a}-${p.b}`)} onClick={() => remove.mutate({ params: { a: p.a, b: p.b } })}>{SK.distinct.remove}</Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function BlocklistTab() {
  const q = useListBlocklistAdminSkillsBlocklistGet({ query: { retry: false } });
  const r = useResult();
  const [norm, setNorm] = useState("");
  const [reason, setReason] = useState("");
  const add = useAddBlocklistAdminSkillsBlocklistPost({ mutation: { onSuccess: () => { r.success(SK.blocklist.added); setNorm(""); setReason(""); }, onError: r.fail } });
  const remove = useRemoveBlocklistAdminSkillsBlocklistDelete({ mutation: { onSuccess: () => r.success(SK.blocklist.removed), onError: r.fail } });
  const items = q.data?.status === 200 ? q.data.data : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!norm.trim()) return r.local(SK.blocklist.local);
    add.mutate({ data: { norm: norm.trim(), reason: reason.trim() || null } });
  };
  return (
    <div className="flex flex-col gap-3" data-testid={sel("blocklist")}>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-end" data-testid={sel("blocklist-form")}>
        <label className="flex flex-1 flex-col gap-1 text-13">{SK.blocklist.norm}<In data-testid={sel("blocklist-norm")} maxLength={120} value={norm} onChange={(e) => setNorm(e.target.value)} /></label>
        <label className="flex flex-1 flex-col gap-1 text-13">{SK.blocklist.reason}<In data-testid={sel("blocklist-reason")} maxLength={300} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <Button type="submit" disabled={add.isPending} data-testid={sel("blocklist-add")}>{SK.blocklist.add}</Button>
      </form>
      <Notice ok={r.ok} err={r.err} />
      <Loading q={q} />
      {items && items.length === 0 && <EmptyState title={SK.blocklist.empty} description={SK.blocklist.emptyText} />}
      {items && items.length > 0 && (
        <ul className="flex flex-col gap-2" data-testid={sel("blocklist-list")}>
          {items.map((b) => (
            <li key={b.norm} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline px-3 py-2" data-testid={sel(`blocklist-row-${b.norm}`)}>
              <span className="text-14"><span className="font-semibold">{b.norm}</span>{b.reason && <span className="text-muted"> · {b.reason}</span>}</span>
              <Button type="button" size="sm" variant="ghost" disabled={remove.isPending} data-testid={sel(`blocklist-remove-${b.norm}`)} onClick={() => remove.mutate({ params: { norm: b.norm } })}>{SK.blocklist.remove}</Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function ProvisionalTab() {
  const q = useListProvisionalAdminSkillsProvisionalGet({ query: { retry: false } });
  const r = useResult();
  const approve = useApproveSkillAdminSkillsSlugApprovePost({ mutation: { onSuccess: (_d, v) => r.success(SK.provisional.approved(nameOf(v.slug))), onError: r.fail } });
  const reject = useRejectSkillAdminSkillsSlugRejectPost({ mutation: { onSuccess: (_d, v) => r.success(SK.provisional.rejectedMsg(nameOf(v.slug))), onError: r.fail } });
  const items = q.data?.status === 200 ? q.data.data : null;
  const nameOf = (slug: string) => items?.find((s) => s.slug === slug)?.name ?? slug;
  const busy = approve.isPending || reject.isPending;
  return (
    <div className="flex flex-col gap-3" data-testid={sel("provisional")}>
      <p className="text-13 text-muted">{SK.provisional.note}</p>
      <Notice ok={r.ok} err={r.err} />
      <Loading q={q} />
      {items && items.length === 0 && <EmptyState title={SK.provisional.empty} description={SK.provisional.emptyText} />}
      {items && items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((s) => (
            <li key={s.slug} data-testid={sel(`prov-row-${s.slug}`)}>
              <Card>
                <CardContent className="flex flex-col gap-2 py-3">
                  <div className="flex flex-wrap items-center gap-2 text-14">
                    <span className="font-semibold">{s.name}</span>
                    <Badge variant="muted">{s.slug}</Badge>
                    {s.type && <Badge>{s.type}</Badge>}
                    <span className="text-13 text-muted">{shortDate(s.created_at)} · {SK.provisional.support(s.support_candidates, s.support_vacancies)}</span>
                  </div>
                  <div className="text-13" data-testid={sel(`prov-draft-${s.slug}`)}>
                    {s.draft ? <><span className="font-semibold">{SK.provisional.draft}: </span>{s.draft.summary}</> : <span className="text-muted">{SK.provisional.noDraft}</span>}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" size="sm" disabled={busy} data-testid={sel(`prov-approve-${s.slug}`)} onClick={() => approve.mutate({ slug: s.slug })}>{SK.provisional.approve}</Button>
                    <Button type="button" size="sm" variant="outline" disabled={busy} data-testid={sel(`prov-reject-${s.slug}`)} onClick={() => reject.mutate({ slug: s.slug })}>{SK.provisional.reject}</Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function HintsTab() {
  const q = useGetHintsAdminSkillsHintsGet({ query: { retry: false } });
  const h = q.data?.status === 200 ? q.data.data : null;
  return (
    <div className="flex flex-col gap-4" data-testid={sel("hints")}>
      <Loading q={q} />
      {h && (
        <>
          <p className="text-13 text-muted" data-testid={sel("hints-updated")}>{h.updated_at ? SK.hints.updated(shortDate(h.updated_at)) : SK.hints.never}</p>
          <section className="flex flex-col gap-2" data-testid={sel("hints-disciplines")}>
            <h2 className="text-16 font-semibold">{SK.hints.disciplines}</h2>
            <p className="text-13 text-muted">{SK.hints.disciplinesText}</p>
            {h.discipline_rules.length === 0 && <p className="text-14 text-muted">{SK.hints.emptyDisciplines}</p>}
            <ul className="flex flex-col gap-2">
              {h.discipline_rules.map((d) => (
                <li key={`${d.discipline}|${d.skill}`} className="flex flex-wrap items-center gap-2 rounded-lg border border-hairline px-3 py-2 text-14">
                  <span className="font-semibold">{d.discipline_name ?? d.discipline}</span>
                  <span className="text-muted">→</span>
                  <span>{d.skill}</span>
                  <Badge variant="muted">{SK.hints.lift(d.lift, d.support)}</Badge>
                </li>
              ))}
            </ul>
          </section>
          <section className="flex flex-col gap-2" data-testid={sel("hints-professions")}>
            <h2 className="text-16 font-semibold">{SK.hints.professions}</h2>
            <p className="text-13 text-muted">{SK.hints.professionsText}</p>
            {h.profession_candidates.length === 0 && <p className="text-14 text-muted">{SK.hints.emptyProfessions}</p>}
            <ul className="flex flex-col gap-2">
              {h.profession_candidates.map((c) => (
                <li key={c.skills.join("|")} className="flex flex-col gap-1 rounded-lg border border-hairline px-3 py-2 text-14">
                  <span className="flex flex-wrap gap-1">{c.skills.map((s) => <Badge key={s}>{s}</Badge>)}</span>
                  <span className="text-13 text-muted">{SK.hints.members(c.support)} · {SK.hints.covered(Math.round(c.covered_by_professions * 100))}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
