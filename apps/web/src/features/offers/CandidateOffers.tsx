import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  Button,
  CircuitLine,
  EmptyState,
  ErrorState,
  MatchWhy,
  OfferCard,
  SalaryRange,
  SectionLabel,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  Skeleton,
  StatusBadge,
  type OfferCardData,
  type OfferStatus,
  type WhyItem,
} from "@fsp/ui";

import {
  useAcceptOfferOffersOfferIdAcceptPost,
  useDeclineOfferOffersOfferIdDeclinePost,
  useGetOfferOffersOfferIdGet,
  useMyInterestsCandidatesMeInterestsGet,
  useMyOffersCandidatesMeOffersGet,
  useRevokeContactsOffersOfferIdContactsRevokePost,
} from "@/api/endpoints/offers/offers";
import { DeclineReason } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { FORMAT_LABEL, percent } from "@/features/employer/text";
import { GRADE_LABEL } from "@/features/profile/text";
import { Conversation, invalidateOffers, Panel, Timeline } from "./parts";
import { isAwaiting, nextSteps, offerTitle, pastSummary, type CandidateOffer } from "./offer-model";
import { ACTIVE_STATUSES, CAND_TEXT as T, CONTACT_LABEL, daysLeft, dateOnly, DECLINE_LABEL, INT_TEXT as IT, offerErrorText } from "./text";
import { WhyYouBlock, whyYouItems } from "./WhyYou";

function cardData(o: CandidateOffer): OfferCardData {
  const tags = o.vacancy ? o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f) : [T.invite];
  if (o.initiator === "candidate") tags.unshift(T.response);
  return {
    company: o.company.name,
    rating: o.company.responsibility_score ?? undefined,
    verified: o.company.verified,
    from: o.salary_from,
    to: o.salary_to,
    title: offerTitle(o),
    tags,
    match: o.match_snapshot ? percent(o.match_snapshot.score) : undefined,
    status: o.status as OfferStatus,
    deadline: isAwaiting(o.status) ? `${dateOnly(o.expires_at)} · осталось ${daysLeft(o.expires_at)} дн.` : undefined,
  };
}

function OfferItem({ o, past }: { o: CandidateOffer; past?: boolean }) {
  const nav = useNavigate();
  return (
    <li className={past ? "opacity-80" : undefined}>
      <OfferCard
        o={cardData(o)}
        onOpen={() => nav(`/me/offers/${o.id}`)}
        extra={
          <>
            {o.below_candidate_min && (
              <p role="status" className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 font-semibold text-warning-fg">{T.belowPlain}</p>
            )}
            {!isAwaiting(o.status) && <p className="text-12 text-muted">Получен {dateOnly(o.created_at)}</p>}
          </>
        }
        className={isAwaiting(o.status) ? "border-brand" : undefined}
      />
    </li>
  );
}

/** Приглашения кандидата (M2): ждущие ответа сверху, прошлые ниже. На 1440 — сетка карточек в ширину контейнера. */
export function CandidateOffers() {
  const q = useMyOffersCandidatesMeOffersGet();
  const all = (q.data?.status === 200 ? q.data.data : []) as unknown as CandidateOffer[];
  const sorted = [...all].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const open = sorted.filter((o) => ACTIVE_STATUSES.includes(o.status));
  const past = sorted.filter((o) => !ACTIVE_STATUSES.includes(o.status));
  const fresh = all.filter((o) => o.status === "sent").length;
  const ps = pastSummary(past);
  const interests = useMyInterestsCandidatesMeInterestsGet();
  const interestCount = interests.data?.status === 200 ? interests.data.data.companies : 0;
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 md:p-6">
      <header className="flex items-center justify-between gap-3">
        <h1 className="font-mono text-24 font-semibold">{T.title}</h1>
        {fresh > 0 && <span className="rounded-full bg-brand px-2.5 py-0.5 font-mono text-12 font-semibold text-on-brand">{T.newCount(fresh)}</span>}
      </header>
      {interestCount > 0 && (
        <Link to="/me/interests" className="flex items-center justify-between gap-3 rounded-xl border border-brand bg-tint-50 p-4 hover:bg-tint-100 focus-visible:outline-2 focus-visible:outline-brand">
          <span className="grid gap-0.5">
            <b className="font-mono text-16">{IT.banner(interestCount)}</b>
            <span className="text-13 text-muted">{IT.bannerHint}</span>
          </span>
          <span aria-hidden className="text-brand-fg">›</span>
        </Link>
      )}
      {q.isPending && (
        <div role="status" aria-label="Загрузка" className="grid gap-3 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      )}
      {q.isError && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
      {q.isSuccess && all.length === 0 && <EmptyState title={T.empty} description={T.emptyHint} />}
      {open.length > 0 && <ul className="grid gap-3 md:grid-cols-2">{open.map((o) => <OfferItem key={o.id} o={o} />)}</ul>}
      {past.length > 0 && (
        <>
          <p className="text-center text-13 text-muted">{T.past}: {T.pastSummary(ps.accepted, ps.declined, ps.expired)}</p>
          <ul className="grid gap-3 md:grid-cols-2">{past.map((o) => <OfferItem key={o.id} o={o} past />)}</ul>
        </>
      )}
    </main>
  );
}

function whyItems(o: CandidateOffer): WhyItem[] {
  if (!o.match_snapshot) return [];
  return o.match_snapshot.explanation.map((i) => ({ kind: i.kind === "plus" ? "ok" : "warn", text: i.text }));
}

export function CandidateOfferDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useGetOfferOffersOfferIdGet(id, { query: { retry: false } });
  const o = q.data?.status === 200 ? (q.data.data as unknown as CandidateOffer) : null;
  const done = () => void invalidateOffers(qc);
  const accept = useAcceptOfferOffersOfferIdAcceptPost({ mutation: { onSuccess: done } });
  const decline = useDeclineOfferOffersOfferIdDeclinePost({
    mutation: {
      onSuccess: () => {
        setSheet(false);
        done();
      },
    },
  });
  const [sheet, setSheet] = useState(false);
  const [revokeSheet, setRevokeSheet] = useState(false);
  const revoke = useRevokeContactsOffersOfferIdContactsRevokePost({
    mutation: {
      onSuccess: () => {
        setRevokeSheet(false);
        done();
      },
    },
  });
  const chat = useRef<HTMLDivElement>(null);
  const answerable = !!o && isAwaiting(o.status);
  const accepted = !!o && ["accepted", "interview", "hired", "not_hired"].includes(o.status);
  const why = o ? whyItems(o) : [];
  const hasWhyYou = !!o && whyYouItems(o.why_you).length > 0;
  const err = accept.error;
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <Link to="/me/offers" className="text-sm font-semibold text-brand-fg hover:underline">← {T.back}</Link>
      {q.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-64" />}
      {q.isError && <ErrorNote>{T.notFound}</ErrorNote>}
      {o && (
        <>
          <header className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h1 className="break-words font-mono text-20 font-semibold">{o.company.name}</h1>
              <p className="text-13 text-muted">
                {offerTitle(o)}
                {o.vacancy ? ` · ${GRADE_LABEL[o.vacancy.grade_min]}–${GRADE_LABEL[o.vacancy.grade_max]}` : ` · ${T.invite.toLowerCase()}`}
              </p>
            </div>
            <StatusBadge status={o.status as OfferStatus} />
          </header>

          {accepted && (
            <section role="status" className="flex flex-col gap-2 rounded-xl border border-success/40 bg-success-bg p-4">
              <h2 className="font-mono text-16 font-semibold text-success">{T.accepted}</h2>
              <p className="text-14">{T.acceptedHint}</p>
              {o.contacts_revoked_at ? (
                <p className="text-13 text-muted">{T.revoked(dateOnly(o.contacts_revoked_at))}</p>
              ) : (
                <Button variant="outline" size="sm" className="self-start" onClick={() => setRevokeSheet(true)}>{T.revoke}</Button>
              )}
            </section>
          )}

          <SalaryRange from={o.salary_from} to={o.salary_to} size="offer" label={T.salaryLabel} />
          <p className="text-13 text-muted">
            {o.vacancy ? o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ") : T.invite}
            {o.contact_method ? ` · ${T.contactVia(CONTACT_LABEL[o.contact_method] ?? o.contact_method)}` : ""}
            {answerable ? ` · ответить до ${dateOnly(o.expires_at)}` : ` · получен ${dateOnly(o.created_at)}`}
          </p>
          {o.below_candidate_min && (
            <p role="status" className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 font-semibold text-warning-fg">{T.belowPlain}</p>
          )}
          {o.decline && <p className="text-14 text-muted">{T.yourDecline(DECLINE_LABEL[o.decline.reason] ?? o.decline.reason)}</p>}

          {(o.message || o.description) && (
            <section className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4">
              {o.message && (
                <>
                  <SectionLabel>{T.fromCompany}</SectionLabel>
                  <p className="whitespace-pre-wrap break-words text-14">{o.message}</p>
                </>
              )}
              {o.description && (
                <>
                  <SectionLabel>{T.description}</SectionLabel>
                  <p className="whitespace-pre-wrap break-words text-14">{o.description}</p>
                </>
              )}
            </section>
          )}

          {hasWhyYou && (
            <Panel title={T.why}>
              <WhyYouBlock why={o.why_you} reliability={o.company.reliability} />
            </Panel>
          )}
          {!hasWhyYou && why.length > 0 && (
            <Panel title={T.why}>
              <MatchWhy items={why} />
            </Panel>
          )}

          {accepted && (
            <Panel title={T.next}>
              <CircuitLine steps={nextSteps(o.status)} />
            </Panel>
          )}

          <div ref={chat}>
            <Conversation offerId={o.id} side="candidate" canWrite={ACTIVE_STATUSES.includes(o.status)} />
          </div>
          <Timeline offerId={o.id} />

          {err && <ErrorNote>{offerErrorText(err)}</ErrorNote>}
          {answerable && (
            <div className="sticky bottom-0 -mx-4 grid gap-2 border-t border-hairline bg-page p-4 md:static md:mx-0 md:border-0 md:bg-transparent md:p-0">
              <Button size="lg" loading={accept.isPending} onClick={() => accept.mutate({ offerId: o.id })}>{T.accept}</Button>
              <div className="grid grid-cols-2 gap-2">
                <Button size="lg" variant="outline" onClick={() => setSheet(true)}>{T.decline}</Button>
                <Button size="lg" variant="ghost" onClick={() => chat.current?.scrollIntoView({ behavior: "smooth" })}>{T.ask}</Button>
              </div>
            </div>
          )}

          <Sheet open={revokeSheet} onOpenChange={setRevokeSheet}>
            <SheetContent side="bottom" className="mx-auto max-w-lg">
              <SheetTitle className="font-mono text-16">{T.revokeTitle}</SheetTitle>
              <SheetDescription>{T.revokeHint}</SheetDescription>
              {revoke.isError && <ErrorNote>{offerErrorText(revoke.error)}</ErrorNote>}
              <div className="mt-3 grid gap-2">
                <Button size="lg" loading={revoke.isPending} onClick={() => revoke.mutate({ offerId: o.id })}>{T.revokeConfirm}</Button>
                <Button variant="link" className="mx-auto flex" onClick={() => setRevokeSheet(false)}>{T.cancel}</Button>
              </div>
            </SheetContent>
          </Sheet>

          <Sheet open={sheet} onOpenChange={setSheet}>
            <SheetContent side="bottom" className="mx-auto max-w-lg">
              <SheetTitle className="font-mono text-16">{T.sheetTitle}</SheetTitle>
              <SheetDescription>{T.sheetHint}</SheetDescription>
              <ul className="mt-3 divide-y divide-hairline">
                {Object.values(DeclineReason).map((r) => (
                  <li key={r}>
                    <button
                      type="button"
                      disabled={decline.isPending}
                      onClick={() => decline.mutate({ offerId: o.id, data: { reason: r, comment: null } })}
                      className="flex h-14 w-full items-center justify-between text-left text-14 hover:bg-tint-50 disabled:opacity-50"
                    >
                      {DECLINE_LABEL[r]}
                      <span aria-hidden className="text-muted">›</span>
                    </button>
                  </li>
                ))}
              </ul>
              {decline.isError && <ErrorNote>{offerErrorText(decline.error)}</ErrorNote>}
              <Button variant="link" className="mx-auto mt-3 flex" onClick={() => setSheet(false)}>{T.cancel}</Button>
            </SheetContent>
          </Sheet>
        </>
      )}
    </main>
  );
}
