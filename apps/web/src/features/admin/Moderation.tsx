import { PAGE } from "@/shared/lib/page";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Card, CardContent, EmptyState, ErrorState, Skeleton } from "@fsp/ui";

import {
  getAdminComplaintsAdminComplaintsGetQueryKey,
  getAdminListAdminCompaniesGetQueryKey,
  useAdminComplaintsAdminComplaintsGet,
  useAdminListAdminCompaniesGet,
  useAdminRejectAdminCompaniesCompanyIdRejectPost,
  useAdminResolveComplaintAdminComplaintsComplaintIdResolvePost,
  useAdminVerifyAdminCompaniesCompanyIdVerifyPost,
} from "@/api/endpoints/admin/admin";
import type { CompanyStatus } from "@/api/model";
import { T } from "./text";

type Tab = "companies" | "complaints";
type ComplaintStatus = "open" | "resolved" | "dismissed";

function Filter<V extends string>({ value, options, labels, onChange }: { value: V | "all"; options: V[]; labels: Record<string, string>; onChange: (v: V | "all") => void }) {
  return (
    <div role="group" className="flex flex-wrap gap-1">
      {(["all", ...options] as (V | "all")[]).map((o) => (
        <button
          key={o}
          type="button"
          aria-pressed={value === o}
          onClick={() => onChange(o)}
          className={`min-h-9 rounded-lg border px-3 text-14 font-semibold ${value === o ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted"}`}
        >
          {o === "all" ? T.mod.statusAll : labels[o]}
        </button>
      ))}
    </div>
  );
}

function Companies() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<CompanyStatus | "all">("pending");
  const q = useAdminListAdminCompaniesGet(status === "all" ? undefined : { status }, { query: { retry: false } });
  const [err, setErr] = useState(false);
  const done = {
    onSuccess: () => {
      setErr(false);
      void qc.invalidateQueries({ queryKey: getAdminListAdminCompaniesGetQueryKey().slice(0, 1) });
    },
    onError: () => setErr(true),
  };
  const verify = useAdminVerifyAdminCompaniesCompanyIdVerifyPost({ mutation: done });
  const reject = useAdminRejectAdminCompaniesCompanyIdRejectPost({ mutation: done });
  const items = q.data?.status === 200 ? q.data.data : null;
  const busy = verify.isPending || reject.isPending;

  return (
    <section aria-label={T.mod.companies} className="flex flex-col gap-3">
      <Filter value={status} options={["pending", "verified", "rejected", "blocked"] as CompanyStatus[]} labels={T.companyStatus} onChange={setStatus} />
      {err && (
        <p role="alert" className="text-14 text-error">
          {T.mod.error}
        </p>
      )}
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.mod.noCompanies} />}
      {items?.map((c) => (
        <Card key={c.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-16 font-semibold">{c.name}</p>
              <p className="text-13 text-muted">
                {c.inn ? `${T.mod.inn} ${c.inn}` : "—"}
                {c.site ? ` · ${c.site}` : ""}
              </p>
              {c.description && <p className="mt-1 line-clamp-2 text-14">{c.description}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={c.status === "verified" ? "success" : c.status === "pending" ? "warning" : "error"}>{T.companyStatus[c.status] ?? c.status}</Badge>
              {c.status !== "verified" && (
                <Button size="sm" disabled={busy} onClick={() => verify.mutate({ companyId: c.id })}>
                  {T.mod.verify}
                </Button>
              )}
              {c.status !== "rejected" && (
                <Button size="sm" variant="outline" disabled={busy} onClick={() => reject.mutate({ companyId: c.id })}>
                  {T.mod.reject}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}

function Complaints() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<ComplaintStatus | "all">("open");
  const q = useAdminComplaintsAdminComplaintsGet(status === "all" ? undefined : { status }, { query: { retry: false } });
  const [err, setErr] = useState(false);
  const resolve = useAdminResolveComplaintAdminComplaintsComplaintIdResolvePost({
    mutation: {
      onSuccess: () => {
        setErr(false);
        void qc.invalidateQueries({ queryKey: getAdminComplaintsAdminComplaintsGetQueryKey().slice(0, 1) });
      },
      onError: () => setErr(true),
    },
  });
  const items = q.data?.status === 200 ? q.data.data : null;

  return (
    <section aria-label={T.mod.complaints} className="flex flex-col gap-3">
      <Filter value={status} options={["open", "resolved", "dismissed"] as ComplaintStatus[]} labels={T.complaintStatus} onChange={setStatus} />
      {err && (
        <p role="alert" className="text-14 text-error">
          {T.mod.error}
        </p>
      )}
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.mod.noComplaints} />}
      {items?.map((c) => (
        <Card key={c.id}>
          <CardContent className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-16 font-semibold">{c.reason}</p>
              <p className="text-13 text-muted">
                {T.mod.company}: {c.company_name ?? "—"} · {T.mod.offer} {c.offer_id.slice(0, 8)}
              </p>
              {c.comment && <p className="mt-1 text-14">{c.comment}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={c.status === "open" ? "warning" : "muted"}>{T.complaintStatus[c.status] ?? c.status}</Badge>
              {c.status === "open" && (
                <>
                  <Button size="sm" disabled={resolve.isPending} onClick={() => resolve.mutate({ complaintId: c.id, data: { decision: "resolved" } })}>
                    {T.mod.resolve}
                  </Button>
                  <Button size="sm" variant="outline" disabled={resolve.isPending} onClick={() => resolve.mutate({ complaintId: c.id, data: { decision: "dismissed" } })}>
                    {T.mod.dismiss}
                  </Button>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}

/** `/federation/moderation` — модерация компаний и жалоб (F3). */
export default function Moderation() {
  const [tab, setTab] = useState<Tab>("companies");
  return (
    <div className={PAGE.wide}>
      <h1 className="text-24 font-semibold">{T.mod.title}</h1>
      <div role="tablist" className="flex gap-1 border-b border-hairline">
        {(["companies", "complaints"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            type="button"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`min-h-10 border-b-2 px-4 text-14 font-semibold ${tab === t ? "border-brand text-ink" : "border-transparent text-muted"}`}
          >
            {T.mod[t]}
          </button>
        ))}
      </div>
      {tab === "companies" ? <Companies /> : <Complaints />}
    </div>
  );
}
