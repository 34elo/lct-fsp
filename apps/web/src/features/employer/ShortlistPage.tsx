import { PAGE } from "@/shared/lib/page";
import { Gloss } from "@/shared/Gloss";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";

import { Button, buttonVariants, Chips, cn, EmptyState, ErrorState, GradeTag, H1, Lbl, Num, Panel, Skeleton, SkillTag, StatusTag } from "@fsp/ui";

import { useNeedCategoriesNeedsNeedIdCategoriesGet } from "@/api/endpoints/needs/needs";
import { useListOffersOffersGet } from "@/api/endpoints/offers/offers";
import { candidateCardCandidatesPseudoIdCardGet, getCandidateCardCandidatesPseudoIdCardGetQueryKey } from "@/api/endpoints/search/search";
import type { CandidateCard, OfferForCompany } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { OfferDialog, type DialogMode, type OfferCandidate } from "@/features/offers/OfferDialog";
import { loadLastNeed, toMatchCard } from "./match-model";
import { interestLabel, interestState, latestOfferByCandidate, nextToInvite } from "./shortlist-model";
import { SHORTLIST_PAGE_TEXT as T } from "./text";

const COLS = "md:grid-cols-[1.1fr_0.6fr_1.7fr_0.9fr_1.1fr_130px]";

interface Target {
  card: CandidateCard;
  mode: DialogMode;
  interest?: OfferForCompany;
}

const asCandidate = (c: CandidateCard): OfferCandidate => ({ pseudoId: c.pseudo_id, pseudonym: c.pseudonym, salaryMin: c.salary_min ?? null });

function Row({ c, offer, onAct }: { c: CandidateCard; offer?: OfferForCompany; onAct: (t: Target) => void }) {
  const d = toMatchCard(c, c.categories?.[0]?.profession ?? c.primary_role ?? "");
  const state = interestState(offer);
  return (
    <li className={cn("grid items-center gap-x-3 gap-y-2 border-t border-hairline px-4 py-3", COLS)} data-testid="shortlist-row">
      <Link to={`/employer/candidates/${c.pseudo_id}?source=match`} className="truncate font-mono text-14 font-semibold text-ink hover:underline">
        {d.pseudonym}
      </Link>
      <span className="justify-self-start">
        <GradeTag claimed={!d.confirmed}>{d.grade}</GradeTag>
      </span>
      <Chips>
        {d.skills.map((s) => (
          <SkillTag key={s.name} name={s.name} level={s.level} state={s.claimed ? "claimed" : "confirmed"} />
        ))}
      </Chips>
      <Num className="text-14 whitespace-nowrap">{d.salary ?? "—"}</Num>
      <span className="justify-self-start">
        <StatusTag state={state === "none" ? "claimed" : "confirmed"}>{interestLabel(offer)}</StatusTag>
      </span>
      {state === "none" && (
        <Button variant="outline" className="h-9 justify-self-start md:justify-self-end" onClick={() => onAct({ card: c, mode: "interest" })}>
          {T.interest}
        </Button>
      )}
      {state === "opened" && (
        <Button className="h-9 justify-self-start md:justify-self-end" onClick={() => onAct({ card: c, mode: "invite", interest: offer })}>
          {T.invite}
        </Button>
      )}
      {(state === "waiting" || state === "other") && offer && (
        <Link to={`/employer/offers/${offer.id}`} className={cn(buttonVariants({ variant: "outline" }), "h-9 justify-self-start md:justify-self-end")}>
          {T.open}
        </Link>
      )}
    </li>
  );
}

function Loading() {
  return (
    <div className="flex flex-col gap-3" aria-hidden data-testid="shortlist-loading">
      <Skeleton className="h-7 w-56" />
      {[0, 1, 2].map((i) => (
        <Panel key={i} className="flex flex-col gap-2.5">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[70%]" />
        </Panel>
      ))}
    </div>
  );
}

const shell = (children: ReactNode) => <div className={PAGE.normal}>{children}</div>;

const header = (action?: ReactNode) => (
  <div className="flex flex-wrap items-center justify-between gap-3">
    <H1 className="text-[22px] md:text-[26px]">
      <Gloss k="shortlist">{T.title}</Gloss>
    </H1>
    {action}
  </div>
);

/**
 * Общий шорт-лист работодателя `/employer/shortlist` (E38-12, бриф §6.12): отмеченные кандидаты потребности
 * (`?need=` или последний запрос) и статус интереса; «Интерес» и «Пригласить» открывают модалку E38-11 на месте.
 */
export default function ShortlistPage() {
  const [params] = useSearchParams();
  const needId = params.get("need") ?? loadLastNeed()?.id ?? null;
  const [target, setTarget] = useState<Target | null>(null);

  const cats = useNeedCategoriesNeedsNeedIdCategoriesGet(needId ?? "", { query: { enabled: !!needId, retry: false } });
  const ids = cats.data?.status === 200 ? (cats.data.data.shortlist ?? []) : [];
  const lost = cats.isError && cats.error instanceof ApiError && cats.error.status === 404;
  const offersQ = useListOffersOffersGet(undefined, { query: { enabled: ids.length > 0 } });
  const offers = latestOfferByCandidate(offersQ.data?.status === 200 ? (offersQ.data.data as OfferForCompany[]) : []);

  const cardQs = useQueries({
    queries: ids.map((id) => ({
      queryKey: getCandidateCardCandidatesPseudoIdCardGetQueryKey(id),
      queryFn: ({ signal }: { signal: AbortSignal }) => candidateCardCandidatesPseudoIdCardGet(id, undefined, { signal }),
      retry: false,
    })),
  });
  const cards: CandidateCard[] = cardQs.flatMap((q) => (q.data?.status === 200 ? [q.data.data as CandidateCard] : []));
  const cardsPending = cardQs.some((q) => q.isPending);
  const cardsFailed = ids.length > 0 && !cardsPending && cards.length === 0;

  const emptyState = (
    <EmptyState
      title={T.empty}
      action={
        <Link to="/employer" className={buttonVariants({ size: "lg" })}>
          {T.toMatch}
        </Link>
      }
    />
  );

  if (!needId || lost) return shell(<>{header()}{emptyState}</>);
  if (cats.isPending) return shell(<Loading />);
  if (cats.isError || offersQ.isError || cardsFailed) {
    const err = [cats.error, offersQ.error, cardQs.find((q) => q.isError)?.error].find((e) => e instanceof ApiError);
    return shell(
      <>
        {header()}
        <ErrorState
          title={T.failed}
          code={err instanceof ApiError ? T.code(err.status) : undefined}
          onRetry={() => {
            void cats.refetch();
            void offersQ.refetch();
            cardQs.forEach((q) => void q.refetch());
          }}
        />
      </>,
    );
  }
  if (ids.length === 0) return shell(<>{header()}{emptyState}</>);
  if (cardsPending || offersQ.isPending) return shell(<Loading />);

  const next = nextToInvite(cards, offers);
  return shell(
    <>
      {header(
        next && (
          <Button size="lg" onClick={() => setTarget({ card: next.card, mode: next.interest ? "invite" : "offer", interest: next.interest })}>
            {T.invite}
          </Button>
        ),
      )}
      <Panel className="overflow-hidden p-0" aria-label={T.list}>
        <div className={cn("hidden min-h-9 items-center gap-3 px-4 md:grid", COLS)} aria-hidden>
          {[T.colCandidate, T.colGrade, T.colSkills, T.colSalary, T.colInterest].map((h) => (
            <Lbl key={h}>{h}</Lbl>
          ))}
          <span />
        </div>
        <ul className="m-0 list-none p-0">
          {cards.map((c) => (
            <Row key={c.pseudo_id} c={c} offer={offers.get(c.pseudo_id)} onAct={setTarget} />
          ))}
        </ul>
      </Panel>
      {target && (
        <OfferDialog open stay mode={target.mode} interest={target.interest} onOpenChange={(v) => !v && setTarget(null)} candidate={asCandidate(target.card)} />
      )}
    </>,
  );
}
