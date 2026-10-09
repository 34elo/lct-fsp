import { PAGE } from "@/shared/lib/page";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, EmptyState, ErrorState, Skeleton, formatRubRange } from "@fsp/ui";

import { useMyApplicationsCandidatesMeApplicationsGet, useWithdrawApplicationCandidatesMeApplicationsOfferIdWithdrawPost } from "@/api/endpoints/offers/offers";
import type { OfferForCandidate } from "@/api/model";
import { ListHeader } from "@/features/offers/offer-cards";
import { ErrorNote } from "@/features/auth/ui";
import { invalidateOffers } from "@/features/offers/parts";
import { dateOnly } from "@/features/offers/text";
import { candTabOf, countBy, filterBy } from "./response-model";
import { RESP_TEXT as T } from "./text";
import { FilterTabs } from "./Tabs";

function Step({ done, children }: { done: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 text-12 text-muted">
      <span aria-hidden className={done ? "h-1.5 w-1.5 rounded-full bg-brand" : "h-1.5 w-1.5 rounded-full border border-muted"} />
      {children}
    </li>
  );
}

function ResponseCard({ o }: { o: OfferForCandidate }) {
  const qc = useQueryClient();
  const withdraw = useWithdrawApplicationCandidatesMeApplicationsOfferIdWithdrawPost({
    mutation: {
      onSuccess: () => {
        void invalidateOffers(qc);
        void qc.invalidateQueries({ queryKey: ["/candidates/me/applications"] });
      },
    },
  });
  const tab = candTabOf(o.status);
  return (
    <li className="flex flex-col gap-3 rounded-2xl border border-hairline bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="break-words font-mono text-16 font-semibold">{o.company.name}</h2>
          <p className="text-13 text-muted">{o.vacancy?.title ?? o.title}</p>
        </div>
        <span className="whitespace-nowrap rounded-full border border-hairline px-2.5 py-0.5 text-12 font-semibold text-muted">{T.statusShort[o.status] ?? o.status}</span>
      </div>
      <p className="font-mono text-20 font-semibold text-brand-deep dark:text-brand-mid">{formatRubRange(o.salary_from, o.salary_to)}</p>
      <ul className="grid gap-1">
        <Step done>{T.sentOn(dateOnly(o.created_at))}</Step>
        <Step done={o.status !== "sent"}>{T.viewedStep}</Step>
        <Step done={tab !== "waiting"}>{T.answerStep}</Step>
      </ul>
      {o.decline?.comment && <p className="text-13 text-muted">{o.decline.comment}</p>}
      {withdraw.isError && <ErrorNote>{T.withdrawError}</ErrorNote>}
      {tab === "waiting" && (
        <Button variant="outline" size="lg" loading={withdraw.isPending} onClick={() => withdraw.mutate({ offerId: o.id })}>
          {withdraw.isPending ? T.withdrawing : T.withdraw}
        </Button>
      )}
      {tab === "invited" && (
        <Link to={`/me/offers/${o.id}`} className="inline-flex h-12 items-center justify-center rounded-lg bg-brand px-5 font-semibold text-on-brand">
          {T.openInvite}
        </Link>
      )}
    </li>
  );
}

/** Мои отклики (R1, кандидат): статусы, отзыв, переход к приглашению. */
export default function CandidateResponses({ filter }: { filter?: ReactNode } = {}) {
  const q = useMyApplicationsCandidatesMeApplicationsGet();
  const all = (q.data?.status === 200 ? q.data.data : []) as OfferForCandidate[];
  const sorted = [...all].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const [tab, setTab] = useState("all");
  const shown = filterBy(sorted, tab, candTabOf);
  return (
    <main className={PAGE.normal}>
      <ListHeader />
      {filter}
      {q.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-48" />}
      {q.isError && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
      {q.isSuccess && all.length === 0 && (
        <EmptyState title={T.candEmpty} description={T.candEmptyHint} action={<Link to="/jobs" className="font-semibold text-brand-fg hover:underline">{T.toJobs}</Link>} />
      )}
      {all.length > 0 && (
        <>
          <FilterTabs label="Фильтр откликов" tabs={T.tabs} value={tab} counts={countBy(sorted, candTabOf)} onChange={setTab} />
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{shown.map((o) => <ResponseCard key={o.id} o={o} />)}</ul>
          <p className="text-12 text-muted">{T.contactsNote}</p>
        </>
      )}
    </main>
  );
}
