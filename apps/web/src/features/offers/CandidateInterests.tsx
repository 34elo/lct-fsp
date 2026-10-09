import { useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button, formatRubRangeShort, OfferCardV2 } from "@fsp/ui";

import {
  useDeclineInterestInterestsOfferIdDeclinePost,
  useMyInterestsCandidatesMeInterestsGet,
  useOpenInterestInterestsOfferIdOpenPost,
} from "@/api/endpoints/offers/offers";
import type { DeclineReason } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { DeclineSheet, LIST_PAGE, ListEmpty, ListError, ListHeader, ListSkeleton, offerCardData } from "./offer-cards";
import type { CandidateOffer } from "./offer-model";
import { invalidateOffers } from "./parts";
import { CAND_TEXT as C, INT_TEXT as T, offerErrorText } from "./text";

function InterestItem({ o, onDecline }: { o: CandidateOffer; onDecline: (id: string) => void }) {
  const qc = useQueryClient();
  const open = useOpenInterestInterestsOfferIdOpenPost({ mutation: { onSuccess: () => void invalidateOffers(qc) } });
  const opened = o.status === "interest_opened";
  return (
    <li className="flex flex-col gap-2">
      <OfferCardV2
        o={offerCardData(o)}
        className={opened ? undefined : "border-brand"}
        actions={
          <>
            {o.below_candidate_min && <p role="status" className="m-0 text-12 font-semibold text-warning-fg">{C.belowPlain}</p>}
            {open.isError && <ErrorNote>{offerErrorText(open.error)}</ErrorNote>}
            {opened ? (
              <p role="status" className="m-0 rounded-lg border border-success/40 bg-success-bg px-3 py-2 text-13 font-semibold text-success">{T.openedShort}</p>
            ) : (
              <Button loading={open.isPending} onClick={() => open.mutate({ offerId: o.id })}>{T.open}</Button>
            )}
            <Button variant="outline" onClick={() => onDecline(o.id)}>{C.reject}</Button>
          </>
        }
      />
      {o.message && (
        <p className="m-0 whitespace-pre-wrap break-words rounded-lg bg-tint-50 px-3 py-2 text-13">
          <span className="mr-2 font-mono text-11 uppercase tracking-[.06em] text-muted">{T.fromCompany}</span>
          {o.message}
        </p>
      )}
    </li>
  );
}

/** Вкладка «Интересы» (E38-14, ADR-026): карточки без контактов, «открыть интерес» / «отклонить» с причиной. */
export function CandidateInterests({ filter }: { filter?: ReactNode } = {}) {
  const qc = useQueryClient();
  const q = useMyInterestsCandidatesMeInterestsGet();
  const summary = q.data?.status === 200 ? q.data.data : null;
  const items = (summary?.items ?? []) as unknown as CandidateOffer[];
  const [declining, setDeclining] = useState<string | null>(null);
  const decline = useDeclineInterestInterestsOfferIdDeclinePost({
    mutation: {
      onSuccess: () => {
        setDeclining(null);
        void invalidateOffers(qc);
      },
    },
  });
  const aside =
    summary && summary.companies > 0
      ? [summary.companies, summary.salary_from_min != null && summary.salary_to_max != null ? formatRubRangeShort(summary.salary_from_min, summary.salary_to_max) : null]
          .filter((x) => x !== null)
          .join(" · ")
      : undefined;
  return (
    <main className={LIST_PAGE}>
      <ListHeader aside={aside} tip={T.tip} />
      {filter}
      {q.isPending && <ListSkeleton />}
      {q.isError && <ListError error={q.error} onRetry={() => void q.refetch()} />}
      {summary && items.length === 0 && <ListEmpty title={T.empty} hint={T.emptyHint} />}
      {items.length > 0 && (
        <>
          <p className="m-0 text-13 text-muted">{T.lead}</p>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">
            {items.map((o) => <InterestItem key={o.id} o={o} onDecline={setDeclining} />)}
          </ul>
        </>
      )}
      <DeclineSheet
        open={declining !== null}
        title={T.sheetTitle}
        hint={T.sheetHint}
        reasons={T.declineReasons}
        pending={decline.isPending}
        error={decline.isError ? offerErrorText(decline.error) : undefined}
        onPick={(r) => declining && decline.mutate({ offerId: declining, data: { reason: r as DeclineReason, comment: null } })}
        onClose={() => setDeclining(null)}
      />
    </main>
  );
}
