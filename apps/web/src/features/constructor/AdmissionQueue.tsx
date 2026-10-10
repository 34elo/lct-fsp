import { PAGE } from "@/shared/lib/page";
import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  Badge,
  Button,
  Card,
  CardContent,
  cn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  EmptyState,
  ErrorState,
  InfoTip,
  ScrollTabs,
  Skeleton,
  Tabs,
  TabsTrigger,
} from "@fsp/ui";

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
import { admissionReasons } from "./model";
import { T } from "./text";
import { AdminPageHeader } from "@/features/admin/PageHeader";

type Status = "draft" | "pilot" | "active" | "quarantine" | "retired";
type Action = "pilot" | "approve" | "quarantine" | "retire";
const STATUSES: Status[] = ["draft", "pilot", "active", "quarantine", "retired"];
const sel = (s: string) => `admission-${s}`;
const fmt = (v: number | null | undefined, d = 2) => (v === null || v === undefined ? "—" : v.toFixed(d));

function titleOf(f: AdminFamilyOut): string {
  return (f.spec as { form?: { title?: string } } | null | undefined)?.form?.title ?? f.slug;
}

function problemText(err: unknown): string {
  if (err instanceof ApiError && err.code && T.queue.problem[err.code]) return T.queue.problem[err.code]!;
  return T.queue.actionError;
}

function Stat({ id, label, tip, value, need, bad }: { id: string; label: string; tip: string; value: string; need?: string; bad?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-lg border border-hairline px-3 py-2" data-testid={sel(`thr-${id}`)} data-failed={bad ?? false}>
      <div className="flex items-center gap-1 text-12 text-muted">
        <span className="min-w-0 truncate">{label}</span>
        <InfoTip label={`Что значит «${label}»`}>{tip}</InfoTip>
      </div>
      <p className={cn("font-mono text-18 font-semibold", bad && "text-error")}>{value}</p>
      {need && <p className="text-12 text-muted">{T.queue.need(need)}</p>}
    </div>
  );
}

function Example({ f }: { f: AdminFamilyOut }) {
  const [full, setFull] = useState(false);
  const ex = f.example;
  if (!ex) return null;
  const long = ex.stem.length > 220 || (ex.options?.length ?? 0) > 0;
  return (
    <section aria-label={T.queue.example} className="flex flex-col gap-2 rounded-lg bg-tint-50 p-3 dark:bg-card" data-testid={sel(`example-${f.id}`)}>
      <h3 className="text-12 font-semibold uppercase text-muted">{T.queue.example}</h3>
      <p className={cn("whitespace-pre-line text-14", !full && "line-clamp-4")} data-testid={sel(`stem-${f.id}`)}>
        {ex.stem}
      </p>
      {full && ex.options && ex.options.length > 0 && (
        <ul className="list-disc pl-5 text-14">
          {ex.options.map((o, i) => (
            <li key={i}>{o}</li>
          ))}
        </ul>
      )}
      {long && (
        <button type="button" className="self-start text-13 font-semibold text-brand-deep underline-offset-2 hover:underline dark:text-brand-mid" onClick={() => setFull(!full)} data-testid={sel(`more-${f.id}`)}>
          {full ? T.queue.hide : T.queue.showAll}
        </button>
      )}
      <p className="text-14" data-testid={sel(`answer-${f.id}`)}>
        <span className="text-muted">{T.queue.answer}: </span>
        <span className="font-semibold">{ex.answer}</span>
        <InfoTip label={`Что такое «${T.queue.answer}»`} className="ml-1 align-middle">
          {T.queue.answerHint}
        </InfoTip>
      </p>
    </section>
  );
}

function Card1({
  f,
  err,
  busy,
  onAction,
  onKey,
}: {
  f: AdminFamilyOut;
  err: string | null;
  busy: boolean;
  onAction: (a: Action, f: AdminFamilyOut) => void;
  onKey: (f: AdminFamilyOut, source: KeyApproveInSource) => void;
}) {
  const failed = f.failed_thresholds ?? [];
  const spec = (f.spec ?? {}) as { key_draft?: Record<string, unknown> | null; form?: { title?: string } };
  const keyApproved = f.key_status === "approved";
  const isSpec = f.source === "spec" || f.source === "llm";
  const canAdmit = f.status === "pilot" || f.status === "quarantine";
  const reasons = canAdmit ? [...failed] : [];
  const closed = canAdmit && (reasons.length > 0 || !keyApproved);
  const professions = (f.professions ?? []).map((p) => p.title);
  const n = f.stats.n ?? f.n;
  const log = f.log ?? [];
  const act = (a: Action, label: string, variant: "default" | "outline" | "ghost", disabled = false) => (
    <Button type="button" size="sm" variant={variant} disabled={busy || disabled} data-testid={sel(`${a}-${f.id}`)} onClick={() => onAction(a, f)}>
      {label}
    </Button>
  );

  return (
    <Card className="h-full" data-testid={sel(`card-${f.id}`)} data-status={f.status} data-grade={f.grade}>
      <CardContent className="flex h-full flex-col gap-3">
        <div className="flex flex-wrap items-center gap-1.5" data-testid={sel(`cell-${f.id}`)}>
          <Badge>{professions.length > 0 ? professions.join(" · ") : T.queue.noProfession}</Badge>
          <Badge variant="muted">{T.queue.grade[f.grade ?? "middle"]}</Badge>
          <Badge variant="muted">{T.skillType[f.skill_type] ?? f.skill_type}</Badge>
          {f.company_id && <Badge variant="dashed">{T.queue.company}</Badge>}
          <Badge variant={f.status === "active" ? "success" : f.status === "quarantine" ? "warning" : "muted"} className="ml-auto">
            {T.status[f.status] ?? f.status}
          </Badge>
        </div>
        <div className="min-w-0">
          <h2 className="text-16 font-semibold" data-testid={sel(`title-${f.id}`)}>
            {titleOf(f)}
          </h2>
          <p className="truncate font-mono text-12 text-muted" data-testid={sel(`slug-${f.id}`)}>
            {f.slug}
          </p>
        </div>

        <Example f={f} />

        <section aria-label={T.queue.stats} className="flex flex-col gap-2">
          <h3 className="text-12 font-semibold uppercase text-muted">{T.queue.stats}</h3>
          <div className="grid grid-cols-2 gap-2">
            <Stat id="n" label={T.queue.statN} tip={T.queue.tipN} value={String(n)} need="≥ 30" bad={failed.includes("n")} />
            <Stat id="p" label={T.queue.statP} tip={T.queue.tipP} value={f.stats.p === null || f.stats.p === undefined ? "—" : `${Math.round(f.stats.p * 100)}%`} />
            <Stat id="b" label={T.queue.statB} tip={T.queue.tipB} value={fmt(f.b, 1)} need="−3…3" bad={failed.includes("b")} />
            <Stat id="r_pb" label={T.queue.statR} tip={T.queue.tipR} value={fmt(f.stats.r_pb)} need="≥ 0.2" bad={failed.includes("r_pb")} />
          </div>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-13 text-muted">
            <span data-testid={sel("thr-seed_spread")} data-failed={failed.includes("seed_spread")} className={cn(failed.includes("seed_spread") && "font-semibold text-error")}>
              {T.queue.spread} {fmt(f.stats.seed_spread)} ({T.queue.need("≤ 0.15")})
              <InfoTip label={`Что значит «${T.queue.spread}»`} className="ml-1 align-middle">
                {T.queue.tipSpread}
              </InfoTip>
            </span>
            <span data-testid={sel("thr-dif")} data-failed={failed.includes("dif") || failed.includes("dif_unmeasured")} className={cn((failed.includes("dif") || failed.includes("dif_unmeasured")) && "font-semibold text-error")}>
              {T.queue.difLabel} {fmt(f.stats.dif)} ({T.queue.need("≤ 0.1")})
              <InfoTip label={`Что значит «${T.queue.difLabel}»`} className="ml-1 align-middle">
                {T.queue.tipDif}
              </InfoTip>
            </span>
          </p>
        </section>

        {closed && reasons.length > 0 && (
          <p data-testid={sel("closed")} className="rounded-lg bg-warning-bg px-3 py-2 text-14 text-warning-fg">
            <span className="font-semibold">{T.queue.closedTitle}</span> {T.queue.closedText(admissionReasons(reasons))}
          </p>
        )}
        {closed && reasons.length === 0 && (
          <p data-testid={sel("closed")} className="rounded-lg bg-warning-bg px-3 py-2 text-14 text-warning-fg">
            <span className="font-semibold">{T.queue.closedTitle}</span> {T.queue.problem.key_not_approved}
          </p>
        )}
        {canAdmit && !closed && (
          <p data-testid={sel("ready")} className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success">
            {T.queue.readyOk}
          </p>
        )}

        {isSpec && !keyApproved && f.status !== "retired" && (
          <section aria-label={T.queue.keys} className="flex flex-col gap-2" data-testid={sel("keys")}>
            <p className="text-13 text-muted">
              <Badge variant="warning" data-testid={sel("key-status")}>
                {T.keyStatus[f.key_status] ?? f.key_status}
              </Badge>{" "}
              {T.queue.keyDraftNote}
            </p>
            {spec.key_draft && (
              <div className="rounded-lg border border-hairline p-2 text-13" data-testid={sel("key-draft")}>
                <p className="font-semibold">{T.queue.keyLlm}</p>
                <pre className="whitespace-pre-wrap font-mono">{JSON.stringify(spec.key_draft)}</pre>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={busy} data-testid={sel("key-author")} onClick={() => onKey(f, "author")}>
                {T.queue.approveAuthor}
              </Button>
              {spec.key_draft && (
                <Button type="button" variant="outline" size="sm" disabled={busy} data-testid={sel("key-llm")} onClick={() => onKey(f, "llm")}>
                  {T.queue.approveLlm}
                </Button>
              )}
            </div>
          </section>
        )}

        <details className="text-13" data-testid={sel(`log-${f.id}`)}>
          <summary className="cursor-pointer text-muted">{T.queue.log}</summary>
          {log.length === 0 ? (
            <p className="mt-1 text-muted">{T.queue.logEmpty}</p>
          ) : (
            <ul className="mt-1 flex flex-col gap-0.5">
              {log.map((l, i) => (
                <li key={i} className="font-mono text-12">
                  {[l.at, l.from, l.to ? `→ ${String(l.to)}` : "", l.reason].filter(Boolean).map(String).join(" ")}
                </li>
              ))}
            </ul>
          )}
        </details>

        {err && (
          <p role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
            {err}
          </p>
        )}

        <div className="mt-auto flex flex-wrap justify-end gap-2 pt-1">
          {f.status === "draft" && act("pilot", T.queue.toPilot, "default", !keyApproved)}
          {f.status !== "retired" && act("retire", T.queue.retire, "ghost")}
          {(f.status === "pilot" || f.status === "active") && act("quarantine", T.queue.quarantine, "outline")}
          {canAdmit && act("approve", T.queue.approve, "default", closed)}
        </div>
      </CardContent>
    </Card>
  );
}

/** Допуск заданий (K2, E39-31): карточки семейств с примером, статистикой пилота и решением админа. */
export default function AdmissionQueue() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<Status>("pilot");
  const [profession, setProfession] = useState<string>("");
  const [pending, setPending] = useState<{ f: AdminFamilyOut; action: Action } | null>(null);
  const [err, setErr] = useState<{ id: string; text: string } | null>(null);
  const q = useAdmissionQueueAdminFamiliesGet({ status }, { query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;

  const opts = {
    mutation: {
      onSuccess: () => {
        setErr(null);
        setPending(null);
        void qc.invalidateQueries({ queryKey: getAdmissionQueueAdminFamiliesGetQueryKey().slice(0, 1) });
      },
      onError: (e: unknown, vars: { familyId: string }) => setErr({ id: vars.familyId, text: problemText(e) }),
    },
  };
  const approve = useApproveAdminFamiliesFamilyIdApprovePost(opts);
  const quarantine = useQuarantineAdminFamiliesFamilyIdQuarantinePost(opts);
  const retire = useRetireAdminFamiliesFamilyIdRetirePost(opts);
  const pilot = useToPilotAdminFamiliesFamilyIdPilotPost(opts);
  const key = useApproveKeyAdminFamiliesFamilyIdKeyPost(opts);
  const busy = approve.isPending || quarantine.isPending || retire.isPending || pilot.isPending || key.isPending;

  const professions = useMemo(() => {
    const m = new Map<string, { title: string; count: number }>();
    for (const f of items ?? []) for (const p of f.professions ?? []) m.set(p.slug, { title: p.title, count: (m.get(p.slug)?.count ?? 0) + 1 });
    return [...m.entries()].sort((a, b) => a[1].title.localeCompare(b[1].title, "ru"));
  }, [items]);
  const shown = useMemo(() => (items ?? []).filter((f) => !profession || (f.professions ?? []).some((p) => p.slug === profession)), [items, profession]);

  const confirm = () => {
    if (!pending) return;
    const data = { familyId: pending.f.id };
    ({ pilot, approve, quarantine, retire })[pending.action].mutate(data);
  };
  const dialogErr = pending && err?.id === pending.f.id ? err.text : null;
  const text = pending ? T.queue.confirm[pending.action]! : null;

  return (
    <div data-testid={sel("page")} className={PAGE.wide}>
      <AdminPageHeader title={T.queue.title} tip={T.queue.lead} />
      <Tabs
        value={status}
        onValueChange={(v) => {
          setStatus(v as Status);
          setProfession("");
          setErr(null);
        }}
      >
        <ScrollTabs aria-label={T.queue.title}>
          {STATUSES.map((s) => (
            <TabsTrigger key={s} value={s} data-testid={sel(`tab-${s}`)}>
              {T.queue.tabs[s]}
            </TabsTrigger>
          ))}
        </ScrollTabs>
      </Tabs>
      <p className="max-w-3xl text-14 text-muted" data-testid={sel("status-help")}>
        {T.queue.statusHelp[status]}
      </p>

      {professions.length > 1 && (
        <div role="group" aria-label={T.queue.filterLabel} className="flex flex-wrap gap-1.5" data-testid={sel("filter")}>
          {[["", { title: T.queue.allProfessions, count: items?.length ?? 0 }] as const, ...professions].map(([slug, p]) => (
            <button
              key={slug || "all"}
              type="button"
              aria-pressed={profession === slug}
              data-testid={sel(`prof-${slug || "all"}`)}
              onClick={() => setProfession(slug)}
              className={cn("min-h-9 rounded-lg border px-3 text-13 font-semibold", profession === slug ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted")}
            >
              {p.title} <span className="font-mono font-normal">{p.count}</span>
            </button>
          ))}
        </div>
      )}

      {q.isLoading && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <Skeleton className="h-72" />
          <Skeleton className="hidden h-72 md:block" />
          <Skeleton className="hidden h-72 xl:block" />
        </div>
      )}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.queue.error} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.queue.emptyTitle} description={T.queue.emptyText} />}
      {items && items.length > 0 && shown.length === 0 && <EmptyState title={T.queue.emptyTitle} description={T.queue.emptyFilter} />}
      {shown.length > 0 && (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" data-testid={sel("list")}>
          {shown.map((f) => (
            <li key={f.id} className="flex min-w-0">
              <Card1
                f={f}
                err={err?.id === f.id && !pending ? err.text : null}
                busy={busy}
                onAction={(action, fam) => {
                  setErr(null);
                  setPending({ f: fam, action });
                }}
                onKey={(fam, source) => key.mutate({ familyId: fam.id, data: { source } })}
              />
            </li>
          ))}
        </ul>
      )}

      <Dialog open={pending !== null} onOpenChange={(o) => !o && setPending(null)}>
        <DialogContent data-testid={sel("confirm")}>
          {pending && text && (
            <>
              <DialogTitle>{text.title}</DialogTitle>
              <DialogDescription>
                <span className="font-semibold">{titleOf(pending.f)}.</span> {text.text}
              </DialogDescription>
              {dialogErr && (
                <p role="alert" data-testid={sel("confirm-error")} className="mt-3 rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
                  {dialogErr}
                </p>
              )}
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <Button type="button" variant="ghost" data-testid={sel("confirm-cancel")} onClick={() => setPending(null)}>
                  {T.queue.cancel}
                </Button>
                <Button type="button" disabled={busy} data-testid={sel("confirm-ok")} onClick={confirm}>
                  {text.ok}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
