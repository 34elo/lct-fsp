import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  Button,
  EmptyState,
  ErrorState,
  OfferCard,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  Skeleton,
  formatRubRange,
  type OfferCardData,
  type OfferStatus,
} from "@fsp/ui";

import {
  useDeclineInterestInterestsOfferIdDeclinePost,
  useMyInterestsCandidatesMeInterestsGet,
  useOpenInterestInterestsOfferIdOpenPost,
} from "@/api/endpoints/offers/offers";
import type { DeclineReason, OfferForCandidate } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { invalidateOffers } from "./parts";
import { daysLeft, dateOnly, DECLINE_LABEL, INT_TEXT as T, offerErrorText } from "./text";
import { WhyYouBlock } from "./WhyYou";

function cardData(o: OfferForCandidate): OfferCardData {
  return {
    company: o.company.name,
    rating: o.company.responsibility_score ?? undefined,
    verified: o.company.verified,
    from: o.salary_from,
    to: o.salary_to,
    title: o.vacancy?.title ?? o.title ?? "Интерес без вакансии",
    tags: o.vacancy ? o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f) : undefined,
    status: o.status as OfferStatus,
    belowExpectation: undefined,
  };
}

function InterestItem({ o, onDecline }: { o: OfferForCandidate; onDecline: (id: string) => void }) {
  const qc = useQueryClient();
  const open = useOpenInterestInterestsOfferIdOpenPost({ mutation: { onSuccess: () => void invalidateOffers(qc) } });
  const opened = o.status === "interest_opened";
  return (
    <li>
      <OfferCard
        o={cardData(o)}
        className={opened ? undefined : "border-brand"}
        extra={
          <>
            {o.below_candidate_min && (
              <p role="status" className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 font-semibold text-warning-fg">Ниже ваших ожиданий</p>
            )}
            {o.message && (
              <p className="whitespace-pre-wrap break-words rounded-lg bg-tint-50 p-3 text-14">
                <span className="mb-1 block font-mono text-11 uppercase tracking-[.06em] text-muted">{T.fromCompany}</span>
                {o.message}
              </p>
            )}
            <WhyYouBlock why={o.why_you} reliability={o.company.reliability} />
            <p className="text-12 text-muted">{T.until(dateOnly(o.expires_at), daysLeft(o.expires_at))}</p>
            {open.isError && <ErrorNote>{offerErrorText(open.error)}</ErrorNote>}
            {opened ? (
              <p role="status" className="rounded-lg border border-success/40 bg-success-bg px-3 py-2 text-13 font-semibold text-success">{T.opened}</p>
            ) : (
              <Button size="lg" loading={open.isPending} onClick={() => open.mutate({ offerId: o.id })}>{T.open}</Button>
            )}
            <Button size="lg" variant="outline" onClick={() => onDecline(o.id)}>{T.notInterested}</Button>
          </>
        }
      />
    </li>
  );
}

/** «Вами интересуются» (ADR-026): агрегат, карточки без контактов, «открыть» / «не интересно» с причиной. */
export function CandidateInterests() {
  const qc = useQueryClient();
  const q = useMyInterestsCandidatesMeInterestsGet();
  const summary = q.data?.status === 200 ? q.data.data : null;
  const items = summary?.items ?? [];
  const [declining, setDeclining] = useState<string | null>(null);
  const decline = useDeclineInterestInterestsOfferIdDeclinePost({
    mutation: {
      onSuccess: () => {
        setDeclining(null);
        void invalidateOffers(qc);
      },
    },
  });
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 md:p-6">
      <Link to="/me/offers" className="text-sm font-semibold text-brand-fg hover:underline">← {T.back}</Link>
      <header className="grid gap-1">
        <h1 className="font-mono text-24 font-semibold">{T.title}</h1>
        <p className="text-14 text-muted">{T.lead}</p>
      </header>
      {q.isPending && (
        <div role="status" aria-label="Загрузка" className="grid gap-3 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      )}
      {q.isError && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
      {summary && summary.companies > 0 && (
        <section aria-label={T.title} className="grid gap-1 rounded-xl border border-brand-mid bg-tint-50 p-4">
          <p className="font-mono text-18 font-semibold">{T.count(summary.companies)}</p>
          {summary.salary_from_min != null && summary.salary_to_max != null && (
            <p className="text-14">{T.range(formatRubRange(summary.salary_from_min, summary.salary_to_max))}</p>
          )}
        </section>
      )}
      {summary && items.length === 0 && <EmptyState title={T.empty} description={T.emptyHint} />}
      {items.length > 0 && (
        <ul className="grid gap-3 md:grid-cols-2">
          {items.map((o) => <InterestItem key={o.id} o={o} onDecline={setDeclining} />)}
        </ul>
      )}
      <Sheet open={declining !== null} onOpenChange={(v) => !v && setDeclining(null)}>
        <SheetContent side="bottom" className="mx-auto max-w-lg">
          <SheetTitle className="font-mono text-16">{T.sheetTitle}</SheetTitle>
          <SheetDescription>{T.sheetHint}</SheetDescription>
          <ul className="mt-3 divide-y divide-hairline">
            {T.declineReasons.map((r) => (
              <li key={r}>
                <button
                  type="button"
                  disabled={decline.isPending}
                  onClick={() => declining && decline.mutate({ offerId: declining, data: { reason: r as DeclineReason, comment: null } })}
                  className="flex h-14 w-full items-center justify-between text-left text-14 hover:bg-tint-50 disabled:opacity-50"
                >
                  {DECLINE_LABEL[r]}
                  <span aria-hidden className="text-muted">›</span>
                </button>
              </li>
            ))}
          </ul>
          {decline.isError && <ErrorNote>{offerErrorText(decline.error)}</ErrorNote>}
          <Button variant="link" className="mx-auto mt-3 flex" onClick={() => setDeclining(null)}>{T.cancel}</Button>
        </SheetContent>
      </Sheet>
    </main>
  );
}
