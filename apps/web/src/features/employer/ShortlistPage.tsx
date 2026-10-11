import { PAGE } from "@/shared/lib/page";
import { Gloss } from "@/shared/Gloss";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQueries, useQueryClient } from "@tanstack/react-query";

import { Button, buttonVariants, Chips, cn, EmptyState, ErrorState, GradeTag, H1, Lbl, Num, Panel, Skeleton, SkillTag, StatusTag } from "@fsp/ui";

import { getShortlistAllShortlistGetQueryKey, useShortlistAllShortlistGet, useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete } from "@/api/endpoints/needs/needs";
import { useListOffersOffersGet } from "@/api/endpoints/offers/offers";
import { candidateCardCandidatesPseudoIdCardGet, getCandidateCardCandidatesPseudoIdCardGetQueryKey } from "@/api/endpoints/search/search";
import type { CandidateCard, OfferForCompany } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { useAuth } from "@/shared/lib/auth";
import { OfferDialog, type DialogMode, type OfferCandidate } from "@/features/offers/OfferDialog";
import { toMatchCard } from "./match-model";
import { COMPARE_MAX, COMPARE_MIN, compareRows, interestLabel, interestState, latestOfferByCandidate, nextToInvite, togglePick } from "./shortlist-model";
import { SHORTLIST_PAGE_TEXT as T } from "./text";

const COLS = "md:grid-cols-[28px_1.1fr_0.6fr_1.7fr_0.9fr_1.1fr_130px_80px]";

interface Target {
  card: CandidateCard;
  mode: DialogMode;
  interest?: OfferForCompany;
}

const asCandidate = (c: CandidateCard): OfferCandidate => ({ pseudoId: c.pseudo_id, pseudonym: c.pseudonym, salaryMin: c.salary_min ?? null });

function Row({
  c, offer, onAct, picked, pickDisabled, onPick, onRemove, removing,
}: {
  c: CandidateCard;
  offer?: OfferForCompany;
  onAct: (t: Target) => void;
  picked: boolean;
  pickDisabled: boolean;
  onPick: () => void;
  onRemove: () => void;
  removing: boolean;
}) {
  const d = toMatchCard(c, c.categories?.[0]?.profession ?? c.primary_role ?? "");
  const state = interestState(offer);
  return (
    <li className={cn("grid items-center gap-x-3 gap-y-2 border-t border-hairline px-4 py-3", COLS)} data-testid="shortlist-row">
      <input
        type="checkbox"
        className="size-4 cursor-pointer accent-[var(--ink,currentColor)]"
        checked={picked}
        disabled={pickDisabled && !picked}
        onChange={onPick}
        aria-label={T.pick(d.pseudonym)}
        data-testid="shortlist-pick"
      />
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
      <button
        type="button"
        className="justify-self-start text-14 text-muted underline-offset-2 hover:text-ink hover:underline disabled:opacity-50 md:justify-self-end"
        onClick={onRemove}
        disabled={removing}
      >
        {T.remove}
      </button>
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
  <div className="flex flex-col gap-2">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <H1 className="text-[22px] md:text-[26px]">
        <Gloss k="shortlist">{T.title}</Gloss>
      </H1>
      {action}
    </div>
    <p className="m-0 max-w-2xl text-14 text-muted">{T.lead}</p>
  </div>
);

/** Сравнение 2–4 кандидатов рядом: колонка на кандидата, строка на признак. */
function Compare({ cards, offers, onClose }: { cards: CandidateCard[]; offers: Map<string, OfferForCompany>; onClose: () => void }) {
  const rows = compareRows(cards, offers);
  const names = cards.map((c) => toMatchCard(c, c.categories?.[0]?.profession ?? c.primary_role ?? "").pseudonym);
  return (
    <Panel className="flex flex-col gap-3" aria-label={T.compareTitle} data-testid="shortlist-compare">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="m-0 font-mono text-[18px] font-semibold">{T.compareTitle}</h2>
        <Button variant="outline" className="h-9" onClick={onClose}>
          {T.compareClose}
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-left text-14" aria-label={T.compareTable}>
          <thead>
            <tr>
              <th scope="col" className="w-28 py-2 pr-3" />
              {cards.map((c, i) => (
                <th key={c.pseudo_id} scope="col" className="py-2 pr-3 align-top">
                  <Link to={`/employer/candidates/${c.pseudo_id}?source=match`} className="font-mono font-semibold text-ink hover:underline">
                    {names[i]}
                  </Link>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.key} className="border-t border-hairline">
                <th scope="row" className="py-2 pr-3 align-top font-normal">
                  <Lbl>{T.rows[r.key]}</Lbl>
                </th>
                {r.cells.map((cell, i) => (
                  <td key={cards[i]!.pseudo_id} className="py-2 pr-3 align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/**
 * Общий шорт-лист работодателя `/employer/shortlist`: все отмеченные кандидаты компании
 * (по всем её запросам, без памяти браузера), статус интереса, сравнение 2–4 кандидатов рядом; «Интерес» и
 * «Пригласить» открывают модалку на месте.
 */
export default function ShortlistPage() {
  const qc = useQueryClient();
  // Без компании шорт-листа нет, а запрос дал бы 404 в консоли нового аккаунта.
  const hasCompany = !!useAuth().me?.company;
  const [target, setTarget] = useState<Target | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [comparing, setComparing] = useState(false);
  const [removeFailed, setRemoveFailed] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const removeMut = useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete();

  const listQ = useShortlistAllShortlistGet({ query: { retry: false, enabled: hasCompany } });
  const items = listQ.data?.status === 200 ? listQ.data.data.items : [];
  const ids = items.map((i) => i.pseudo_id);
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
      description={T.emptyHint}
      action={
        <Link to="/employer" className={buttonVariants({ size: "lg" })}>
          {T.toMatch}
        </Link>
      }
    />
  );

  if (!hasCompany) return shell(<>{header()}{emptyState}</>);
  if (listQ.isPending) return shell(<Loading />);
  if (listQ.isError || offersQ.isError || cardsFailed) {
    const err = [listQ.error, offersQ.error, cardQs.find((q) => q.isError)?.error].find((e) => e instanceof ApiError);
    return shell(
      <>
        {header()}
        <ErrorState
          title={T.failed}
          code={err instanceof ApiError ? T.code(err.status) : undefined}
          onRetry={() => {
            void listQ.refetch();
            void offersQ.refetch();
            cardQs.forEach((q) => void q.refetch());
          }}
        />
      </>,
    );
  }
  if (ids.length === 0) return shell(<>{header()}{emptyState}</>);
  if (cardsPending || offersQ.isPending) return shell(<Loading />);

  const needOf = new Map(items.map((i) => [i.pseudo_id, i.need_id]));
  const remove = (pseudoId: string) => {
    const needId = needOf.get(pseudoId);
    if (!needId) return;
    setRemoveFailed(false);
    setRemoving(pseudoId);
    removeMut.mutate(
      { needId, pseudoId },
      {
        onSuccess: () => {
          setPicked((p) => p.filter((x) => x !== pseudoId));
          void qc.invalidateQueries({ queryKey: getShortlistAllShortlistGetQueryKey() });
        },
        onError: () => setRemoveFailed(true),
        onSettled: () => setRemoving(null),
      },
    );
  };

  const chosen = picked.map((id) => cards.find((c) => c.pseudo_id === id)).filter((c): c is CandidateCard => !!c);
  const canCompare = chosen.length >= COMPARE_MIN;
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
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" className="h-9" disabled={!canCompare} onClick={() => setComparing(true)}>
          {T.compare(chosen.length)}
        </Button>
        <span className="text-14 text-muted" role="status">
          {chosen.length >= COMPARE_MAX ? T.compareMax : T.compareHint}
        </span>
      </div>
      {removeFailed && (
        <p className="m-0 text-14 text-error" role="alert">
          {T.removeFailed}
        </p>
      )}
      {comparing && canCompare && <Compare cards={chosen} offers={offers} onClose={() => setComparing(false)} />}
      <Panel className="overflow-hidden p-0" aria-label={T.list}>
        <div className={cn("hidden min-h-9 items-center gap-3 px-4 md:grid", COLS)} aria-hidden>
          <span />
          {[T.colCandidate, T.colGrade, T.colSkills, T.colSalary, T.colInterest].map((h) => (
            <Lbl key={h}>{h}</Lbl>
          ))}
          <span />
          <span />
        </div>
        <ul className="m-0 list-none p-0">
          {cards.map((c) => (
            <Row
              key={c.pseudo_id}
              c={c}
              offer={offers.get(c.pseudo_id)}
              onAct={setTarget}
              picked={picked.includes(c.pseudo_id)}
              pickDisabled={picked.length >= COMPARE_MAX}
              onPick={() => setPicked((p) => togglePick(p, c.pseudo_id))}
              onRemove={() => remove(c.pseudo_id)}
              removing={removing === c.pseudo_id}
            />
          ))}
        </ul>
      </Panel>
      {target && (
        <OfferDialog open stay mode={target.mode} interest={target.interest} onOpenChange={(v) => !v && setTarget(null)} candidate={asCandidate(target.card)} />
      )}
    </>,
  );
}
