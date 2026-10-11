import { PAGE } from "@/shared/lib/page";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import type { ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  Avatar,
  Button,
  CircuitLine,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  Markdown,
  MatchWhy,
  OfferCardV2,
  SalaryRange,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  Skeleton,
  StatusBadge,
  type OfferStatus,
  type WhyItem,
} from "@fsp/ui";

import {
  useAcceptOfferOffersOfferIdAcceptPost,
  useDeclineOfferOffersOfferIdDeclinePost,
  useGetOfferOffersOfferIdGet,
  useMyOffersCandidatesMeOffersGet,
  useRevokeContactsOffersOfferIdContactsRevokePost,
} from "@/api/endpoints/offers/offers";
import { DeclineReason } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { avatarSrc } from "@/shared/lib/avatar";
import { FORMAT_LABEL } from "@/features/employer/text";
import { GRADE_LABEL } from "@/features/profile/text";
import { ContactsCard, invalidateOffers, MessageCard, Panel, Timeline } from "./parts";
import { DeclineSheet, DetailLink, LIST_PAGE, ListEmpty, ListError, ListHeader, ListSkeleton, offerCardData } from "./offer-cards";
import { isAwaiting, nextSteps, offerTitle, pastSummary, type CandidateOffer } from "./offer-model";
import { ACTIVE_STATUSES, CAND_TEXT as T, CONTACT_LABEL, dateOnly, DECLINE_LABEL, offerErrorText } from "./text";
import { WhyYouBlock, whyYouItems } from "./WhyYou";
import CandidateResponses from "@/features/responses/CandidateResponses";
import { CandidateInterests } from "./CandidateInterests";
import { ShowFilter, useShow } from "./ShowFilter";

function OfferItem({ o, onDecline }: { o: CandidateOffer; onDecline: (id: string) => void }) {
  const qc = useQueryClient();
  const accept = useAcceptOfferOffersOfferIdAcceptPost({ mutation: { onSuccess: () => void invalidateOffers(qc) } });
  const awaiting = isAwaiting(o.status);
  const closed = ["declined", "expired", "withdrawn"].includes(o.status);
  const title = offerTitle(o);
  return (
    <li>
      <OfferCardV2
        o={offerCardData(o)}
        dimmed={closed}
        className={awaiting ? "border-brand" : undefined}
        actions={
          <>
            {o.below_candidate_min && awaiting && <p role="status" className="m-0 text-12 font-semibold text-warning-fg">{T.belowPlain}</p>}
            {awaiting ? (
              <>
                {accept.isError && <ErrorNote>{offerErrorText(accept.error)}</ErrorNote>}
                <Button loading={accept.isPending} aria-label={`${T.accept}: ${title}`} onClick={() => accept.mutate({ offerId: o.id })}>{T.accept}</Button>
                <Button variant="outline" onClick={() => onDecline(o.id)}>{T.reject}</Button>
              </>
            ) : (
              <StatusBadge status={o.status as OfferStatus} className="self-start" />
            )}
            <DetailLink id={o.id} />
          </>
        }
      />
    </li>
  );
}

/** Вкладка «Приглашения»: ждущие ответа сверху, прошлые приглушены ниже; отклики кандидата — в своей вкладке. */
/** «Приглашения» кандидата: один экран с фильтром — приглашения, интересы компаний, свои отклики. */
export function CandidateOffers() {
  const show = useShow(["offers", "interests", "responses"] as const);
  const filter = <ShowFilter options={T.filter} label={T.filterLabel} />;
  if (show === "interests") return <CandidateInterests filter={filter} />;
  if (show === "responses") return <CandidateResponses filter={filter} />;
  return <OffersList filter={filter} />;
}

function OffersList({ filter }: { filter: ReactNode }) {
  const qc = useQueryClient();
  const q = useMyOffersCandidatesMeOffersGet();
  const all = ((q.data?.status === 200 ? q.data.data : []) as unknown as CandidateOffer[]).filter((o) => o.initiator !== "candidate");
  const sorted = [...all].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const open = sorted.filter((o) => ACTIVE_STATUSES.includes(o.status));
  const past = sorted.filter((o) => !ACTIVE_STATUSES.includes(o.status));
  const ps = pastSummary(past);
  const [declining, setDeclining] = useState<string | null>(null);
  const decline = useDeclineOfferOffersOfferIdDeclinePost({
    mutation: {
      onSuccess: () => {
        setDeclining(null);
        void invalidateOffers(qc);
      },
    },
  });
  return (
    <main className={LIST_PAGE}>
      <ListHeader />
      {filter}
      {q.isPending && <ListSkeleton />}
      {q.isError && <ListError error={q.error} onRetry={() => void q.refetch()} />}
      {q.isSuccess && all.length === 0 && <ListEmpty title={T.empty} />}
      {open.length > 0 && <ul className="m-0 flex list-none flex-col gap-4 p-0">{open.map((o) => <OfferItem key={o.id} o={o} onDecline={setDeclining} />)}</ul>}
      {past.length > 0 && (
        <>
          <p className="m-0 text-center text-13 text-muted">{T.past}: {T.pastSummary(ps.accepted, ps.declined, ps.expired)}</p>
          <ul className="m-0 flex list-none flex-col gap-4 p-0">{past.map((o) => <OfferItem key={o.id} o={o} onDecline={setDeclining} />)}</ul>
        </>
      )}
      <DeclineSheet
        open={declining !== null}
        title={T.sheetTitle}
        hint={T.sheetHint}
        reasons={Object.values(DeclineReason)}
        pending={decline.isPending}
        error={decline.isError ? offerErrorText(decline.error) : undefined}
        onPick={(r) => declining && decline.mutate({ offerId: declining, data: { reason: r as DeclineReason, comment: null } })}
        onClose={() => setDeclining(null)}
      />
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
  const answerable = !!o && isAwaiting(o.status);
  const accepted = !!o && ["accepted", "interview", "hired", "not_hired"].includes(o.status);
  const why = o ? whyItems(o) : [];
  const hasWhyYou = !!o && whyYouItems(o.why_you).length > 0;
  const err = accept.error;
  const contacts = o?.company_contacts ?? null;
  return (
    <main className={PAGE.normal}>
      <Link to="/me/offers" className="text-sm font-semibold text-brand-fg hover:underline">← {T.back}</Link>
      {q.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-64" />}
      {q.isError && <ErrorNote>{T.notFound}</ErrorNote>}
      {o && (
        <>
          <header className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-3">
              <Avatar name={o.company.name} src={avatarSrc(o.company.logo_url)} size={48} className="rounded-xl" />
              <div className="min-w-0">
                <h1 className="break-words font-mono text-20 font-semibold">{o.company.name}</h1>
                <p className="text-13 text-muted">
                  {offerTitle(o)}
                  {o.vacancy ? ` · ${GRADE_LABEL[o.vacancy.grade_min]}–${GRADE_LABEL[o.vacancy.grade_max]}` : ` · ${T.invite.toLowerCase()}`}
                </p>
              </div>
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

          <div className="grid items-start gap-4 lg:grid-cols-12">
            <div className="flex min-w-0 flex-col gap-4 lg:col-span-8">
              <Panel title={T.conditions}>
                <SalaryRange from={o.salary_from} to={o.salary_to} size="offer" label={T.salaryLabel} />
                <p className="text-13 text-muted">
                  {o.vacancy ? o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ") : T.invite}
                  {o.contact_method ? ` · ${T.contactVia(CONTACT_LABEL[o.contact_method] ?? o.contact_method)}` : ""}
                  {answerable ? ` · ответить до ${dateOnly(o.expires_at)}` : ` · получен ${dateOnly(o.created_at)}`}
                </p>
                {o.below_candidate_min && (
                  <p role="status" className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 font-semibold text-warning-fg">{T.belowPlain}</p>
                )}
                {o.task && (
                  <p data-testid="offer-task" className="text-14">
                    {o.task.answered_at ? T.taskAnswered : T.task(o.task.title, o.task.minutes, dateOnly(o.task.deadline_at))}
                  </p>
                )}
                {o.decline && <p className="text-14 text-muted">{T.yourDecline(DECLINE_LABEL[o.decline.reason] ?? o.decline.reason)}</p>}
                {o.description && <MessageCard label={T.description} text={o.description} />}
                {o.message && <MessageCard label={T.fromCompany} text={o.message} testId="offer-message" />}
              </Panel>

              {o.company.description && (
                <Panel title={T.aboutCompany}>
                  <Markdown data-testid="offer-company-about">{o.company.description}</Markdown>
                </Panel>
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

              {err && <ErrorNote>{offerErrorText(err)}</ErrorNote>}
              {answerable && (
                <Panel title={T.answerTitle}>
                  <p className="text-13 text-muted">{T.answerHint}</p>
                  <div className="sticky bottom-0 -mx-4 grid gap-2 border-t border-hairline bg-page p-4 md:static md:mx-0 md:grid-cols-2 md:border-0 md:bg-transparent md:p-0">
                    <Button size="lg" loading={accept.isPending} onClick={() => accept.mutate({ offerId: o.id })}>{T.accept}</Button>
                    <Button size="lg" variant="outline" onClick={() => setSheet(true)}>{T.decline}</Button>
                  </div>
                </Panel>
              )}
            </div>

            <div className="flex min-w-0 flex-col gap-4 lg:col-span-4">
              {o.sender && (
                <section className="flex items-center gap-3 rounded-xl border border-hairline bg-card p-4" aria-label={T.sentBy} data-testid="offer-sender">
                  <Avatar name={o.sender.full_name} src={avatarSrc(o.sender.avatar_url)} size={44} />
                  <div className="flex min-w-0 flex-col">
                    <span className="text-12 text-muted">{T.sentBy}</span>
                    <span className="truncate font-medium">{o.sender.full_name}</span>
                    {o.sender.position && <span className="truncate text-13 text-muted">{`${o.sender.position} · ${o.company.name}`}</span>}
                  </div>
                </section>
              )}
              {contacts && <ContactsCard title={T.companyContacts} hint={T.companyContactsHint} contacts={contacts} testId="company-contacts" />}
              <Timeline offerId={o.id} />
              {accepted && (
                <Panel title={T.next}>
                  <CircuitLine steps={nextSteps(o.status)} />
                </Panel>
              )}
            </div>
          </div>

          <Dialog open={revokeSheet} onOpenChange={setRevokeSheet}>
            <DialogContent data-testid="revoke-dialog">
              <DialogTitle className="font-mono text-16">{T.revokeTitle}</DialogTitle>
              <DialogDescription>{T.revokeHint}</DialogDescription>
              {revoke.isError && <ErrorNote>{offerErrorText(revoke.error)}</ErrorNote>}
              <div className="mt-3 grid gap-2">
                <Button size="lg" loading={revoke.isPending} onClick={() => revoke.mutate({ offerId: o.id })}>{T.revokeConfirm}</Button>
                <Button variant="link" className="mx-auto flex" onClick={() => setRevokeSheet(false)}>{T.cancel}</Button>
              </div>
            </DialogContent>
          </Dialog>

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
