import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Card, CardContent, cn, EmptyState, ErrorState, Skeleton } from "@fsp/ui";

import {
  getAdmissionQueueAdminFamiliesGetQueryKey,
  useAdmissionQueueAdminFamiliesGet,
  useApproveAdminFamiliesFamilyIdApprovePost,
  useApproveKeyAdminFamiliesFamilyIdKeyPost,
  useQuarantineAdminFamiliesFamilyIdQuarantinePost,
  useRetireAdminFamiliesFamilyIdRetirePost,
  useToPilotAdminFamiliesFamilyIdPilotPost,
} from "@/api/endpoints/admin/admin";
import type { AdminFamilyOut, KeyApproveInSource } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { admissionClosedNames } from "./model";
import { T } from "./text";

type Status = "draft" | "pilot" | "active" | "quarantine" | "retired";
const STATUSES: Status[] = ["draft", "pilot", "active", "quarantine", "retired"];
const sel = (s: string) => `admission-${s}`;
const fmt = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : v.toFixed(d));

function metric(f: AdminFamilyOut, id: string): number | null | undefined {
  switch (id) {
    case "n":
      return f.stats.n ?? f.n;
    case "r_pb":
      return f.stats.r_pb;
    case "b":
      return Math.abs(f.b);
    case "seed_spread":
      return f.stats.seed_spread;
    default:
      return f.stats.dif;
  }
}

function problemText(err: unknown): string {
  if (err instanceof ApiError && err.code && T.queue.problem[err.code]) return T.queue.problem[err.code]!;
  return T.queue.actionError;
}

function Detail({ f, onDone }: { f: AdminFamilyOut; onDone: () => void }) {
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const opts = {
    mutation: {
      onSuccess: () => {
        setErr(null);
        void qc.invalidateQueries({ queryKey: getAdmissionQueueAdminFamiliesGetQueryKey().slice(0, 1) });
        onDone();
      },
      onError: (e: unknown) => setErr(problemText(e)),
    },
  };
  const approve = useApproveAdminFamiliesFamilyIdApprovePost(opts);
  const quarantine = useQuarantineAdminFamiliesFamilyIdQuarantinePost(opts);
  const retire = useRetireAdminFamiliesFamilyIdRetirePost(opts);
  const pilot = useToPilotAdminFamiliesFamilyIdPilotPost(opts);
  const key = useApproveKeyAdminFamiliesFamilyIdKeyPost(opts);
  const busy = approve.isPending || quarantine.isPending || retire.isPending || pilot.isPending || key.isPending;

  const failed = f.failed_thresholds ?? [];
  const spec = (f.spec ?? {}) as { key_draft?: Record<string, unknown> | null; author?: unknown; form?: { title?: string } };
  const keyApproved = f.key_status === "approved";
  const isSpec = f.source === "spec" || f.source === "llm";
  const canAdmit = f.status === "pilot" || f.status === "quarantine";
  const closed = canAdmit && (failed.length > 0 || !keyApproved);
  const approveKey = (source: KeyApproveInSource) => key.mutate({ familyId: f.id, data: { source } });

  return (
    <Card data-testid={sel("detail")}>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-16 font-semibold break-all">{f.slug}</h2>
            <p className="text-13 text-muted">{spec.form?.title ?? ""}</p>
          </div>
          <Badge>{T.status[f.status] ?? f.status}</Badge>
        </div>

        <section aria-label={T.queue.thresholds}>
          <h3 className="mb-1 text-14 font-semibold">{T.queue.thresholds}</h3>
          <table className="w-full text-14" data-testid={sel("thresholds")}>
            <thead>
              <tr className="text-left text-13 text-muted">
                <th className="py-1 font-normal">{T.queue.thr.name}</th>
                <th className="font-normal">{T.queue.thr.now}</th>
                <th className="font-normal">{T.queue.thr.need}</th>
              </tr>
            </thead>
            <tbody>
              {T.queue.thrRows.map((r) => {
                const bad = failed.includes(r.id);
                return (
                  <tr key={r.id} data-testid={sel(`thr-${r.id}`)} data-failed={bad} className="border-t border-hairline">
                    <td className="py-1">{r.label}</td>
                    <td className={cn("font-mono", bad && "font-semibold text-error")}>{fmt(metric(f, r.id), r.id === "n" ? 0 : 2)}</td>
                    <td className="font-mono text-muted">{r.need}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <section aria-label={T.queue.keys} className="flex flex-col gap-2" data-testid={sel("keys")}>
          <h3 className="text-14 font-semibold">{T.queue.keys}</h3>
          <div className="flex flex-wrap items-center gap-2 text-13">
            <span className="text-muted">{T.queue.keyAuthor}</span>
            <Badge variant={keyApproved ? "success" : "warning"} data-testid={sel("key-status")}>{T.keyStatus[f.key_status] ?? f.key_status}</Badge>
          </div>
          {spec.key_draft && (
            <div className="rounded-lg border border-hairline p-2 text-13" data-testid={sel("key-draft")}>
              <p className="font-semibold">{T.queue.keyLlm}</p>
              <pre className="whitespace-pre-wrap font-mono">{JSON.stringify(spec.key_draft)}</pre>
            </div>
          )}
          <p className="text-13 text-muted">
            {T.queue.keyEmpirical}: {T.queue.keyEmpiricalNo}
          </p>
          <p className="text-13 text-muted">
            {T.queue.aiSolvable}: {fmt(f.ai_solvable)}
          </p>
          <p className="text-13 text-muted">{keyApproved ? T.queue.keyApprovedNote : T.queue.keyDraftNote}</p>
          {isSpec && !keyApproved && f.status !== "retired" && (
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={busy} data-testid={sel("key-author")} onClick={() => approveKey("author")}>
                {T.queue.approveAuthor}
              </Button>
              {spec.key_draft && (
                <Button type="button" variant="outline" size="sm" disabled={busy} data-testid={sel("key-llm")} onClick={() => approveKey("llm")}>
                  {T.queue.approveLlm}
                </Button>
              )}
            </div>
          )}
        </section>

        <section aria-label={T.queue.log}>
          <h3 className="mb-1 text-14 font-semibold">{T.queue.log}</h3>
          {(f.log ?? []).length === 0 ? (
            <p className="text-13 text-muted">{T.queue.logEmpty}</p>
          ) : (
            <ul className="flex flex-col gap-0.5 text-13" data-testid={sel("log")}>
              {(f.log ?? []).map((l, i) => (
                <li key={i} className="font-mono">
                  {[l.at, l.from, l.to ? `→ ${String(l.to)}` : "", l.reason].filter(Boolean).map(String).join(" ")}
                </li>
              ))}
            </ul>
          )}
        </section>

        {closed && failed.length > 0 && (
          <p data-testid={sel("closed")} className="rounded-lg bg-warning-bg px-3 py-2 text-14 text-warning-fg">
            <span className="font-semibold">{T.queue.closedTitle}</span> {T.queue.closedText(admissionClosedNames(failed))}
          </p>
        )}
        {closed && failed.length === 0 && !keyApproved && (
          <p data-testid={sel("closed")} className="rounded-lg bg-warning-bg px-3 py-2 text-14 text-warning-fg">
            <span className="font-semibold">{T.queue.closedTitle}</span> {T.queue.problem.key_not_approved}
          </p>
        )}
        {err && (
          <p role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
            {err}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          {f.status === "draft" && (
            <Button type="button" disabled={busy || !keyApproved} data-testid={sel("pilot")} onClick={() => pilot.mutate({ familyId: f.id })}>
              {T.queue.toPilot}
            </Button>
          )}
          {f.status !== "retired" && (
            <Button type="button" variant="ghost" disabled={busy} data-testid={sel("retire")} onClick={() => retire.mutate({ familyId: f.id })}>
              {T.queue.retire}
            </Button>
          )}
          {(f.status === "pilot" || f.status === "active") && (
            <Button type="button" variant="outline" disabled={busy} data-testid={sel("quarantine")} onClick={() => quarantine.mutate({ familyId: f.id })}>
              {T.queue.quarantine}
            </Button>
          )}
          {canAdmit && (
            <Button type="button" disabled={busy || closed} data-testid={sel("approve")} onClick={() => approve.mutate({ familyId: f.id })}>
              {T.queue.approve}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/** K2: очередь допуска семейств заданий (админ ФСП). */
export default function AdmissionQueue() {
  const [status, setStatus] = useState<Status>("pilot");
  const [openId, setOpenId] = useState<string | null>(null);
  const q = useAdmissionQueueAdminFamiliesGet({ status }, { query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;
  const open = items?.find((x) => x.id === openId) ?? null;

  return (
    <div data-testid={sel("page")} className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{T.queue.title}</h1>
        <p className="text-14 text-muted">{T.queue.lead}</p>
      </header>
      <div role="tablist" aria-label={T.queue.title} className="flex flex-wrap gap-1">
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            role="tab"
            aria-selected={status === s}
            data-testid={sel(`tab-${s}`)}
            onClick={() => {
              setStatus(s);
              setOpenId(null);
            }}
            className={cn("min-h-9 rounded-lg border px-3 text-14 font-semibold", status === s ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted")}
          >
            {T.queue.tabs[s]}
          </button>
        ))}
      </div>
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.queue.error} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.queue.emptyTitle} description={T.queue.emptyText} />}
      {items && items.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <ul className="flex flex-col gap-2" data-testid={sel("list")}>
            {items.map((f) => {
              const failed = (f.failed_thresholds ?? []).length > 0;
              return (
                <li key={f.id}>
                  <Card className={cn(openId === f.id && "border-brand")}>
                    <CardContent className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-mono text-14 font-semibold" data-testid={sel(`slug-${f.id}`)}>{f.slug}</p>
                        <p className="text-13 text-muted">
                          {[T.skillType[f.skill_type] ?? f.skill_type, T.queue.level(f.level), f.kind, T.source[f.source] ?? f.source, f.company_id ? T.queue.company : ""].filter(Boolean).join(" · ")}
                        </p>
                        <p className="font-mono text-13 text-muted">
                          {`n=${f.stats.n ?? f.n} · r_pb ${fmt(f.stats.r_pb)} · b ${fmt(f.b, 1)} · ${T.queue.colSeeds.toLowerCase()} ${fmt(f.stats.seed_spread)} · DIF ${fmt(f.stats.dif)}`}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {(f.status === "pilot" || f.status === "quarantine") && (
                          <Badge variant={failed ? "warning" : "success"} data-testid={sel(`admit-${f.id}`)}>
                            {failed ? T.queue.admitNo : T.queue.admitOk}
                          </Badge>
                        )}
                        <Button type="button" size="sm" variant="outline" data-testid={sel(`open-${f.id}`)} onClick={() => setOpenId(openId === f.id ? null : f.id)}>
                          {openId === f.id ? T.queue.close : T.queue.open}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </li>
              );
            })}
          </ul>
          {open && <Detail key={open.id} f={open} onDone={() => setOpenId(null)} />}
        </div>
      )}
    </div>
  );
}
