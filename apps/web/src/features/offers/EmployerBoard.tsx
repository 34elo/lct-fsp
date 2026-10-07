import { useState } from "react";
import { Link } from "react-router-dom";

import { ConstellationAvatar, EmptyState, ErrorState, SectionLabel, Skeleton, StatusBadge, Zap, buttonVariants, cn, formatRubRangeShort, type OfferStatus } from "@fsp/ui";

import { useListOffersOffersGet } from "@/api/endpoints/offers/offers";
import type { OfferForCompany } from "@/api/model";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { BOARD_COLUMNS, boardStats, declineBreakdown, groupByColumn, type BoardColumn } from "./offer-model";
import { BOARD_TEXT as T, DECLINE_LABEL, OFFER_STATUS_LABEL, dateOnly } from "./text";

const shortDate = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });

/** Карточка приглашения на доске: кандидат, вилка, статус, даты. */
function OfferCardRow({ o }: { o: OfferForCompany }) {
  const c = o.candidate;
  const name = c?.pseudonym ?? T.deleted;
  const sub = c ? [c.primary_role && roleLabel(c.primary_role), c.grade && (GRADE_LABEL[c.grade] ?? c.grade)].filter(Boolean).join(" · ") : "";
  const waiting = o.status === "sent" || o.status === "viewed" || o.status === "interest" || o.status === "interest_opened";
  const reason = o.decline ? (DECLINE_LABEL[o.decline.reason] ?? o.decline.reason).toLowerCase() : null;
  return (
    <li>
      <Link
        to={`/employer/offers/${o.id}`}
        aria-label={`${name}, ${OFFER_STATUS_LABEL[o.status] ?? o.status}`}
        className="grid gap-2.5 rounded-xl border border-hairline bg-card p-3 shadow-xs hover:border-brand-mid focus-visible:outline-2 focus-visible:outline-brand"
      >
        <span className="flex items-center gap-2.5">
          {c && <ConstellationAvatar seed={c.avatar_seed} size={36} />}
          <span className="grid min-w-0">
            <span className="break-words font-mono text-13 font-semibold">{name}</span>
            {sub && <span className="text-12 text-muted">{sub}</span>}
          </span>
        </span>
        <span className="font-mono text-14 font-semibold">{formatRubRangeShort(o.salary_from, o.salary_to)}</span>
        <span className="flex flex-wrap items-center gap-1.5">
          <StatusBadge status={o.status as OfferStatus} />
          {reason && <span className="text-12 text-error">{T.reason(reason)}</span>}
        </span>
        <span className="text-12 text-muted">
          {shortDate(o.created_at)}
          {waiting && <> · {T.replyBy(dateOnly(o.expires_at))}</>}
        </span>
        {(o.awaiting_reply_from === "company" || o.status === "interest_opened") && <span className="text-12 font-semibold text-brand-fg">{T.yourTurn}</span>}
      </Link>
    </li>
  );
}

function Column({ id, items, hiddenOnPhone }: { id: BoardColumn; items: OfferForCompany[]; hiddenOnPhone: boolean }) {
  const title = T.columns[id];
  return (
    <section aria-label={title} className={cn("min-w-0 flex-col gap-2.5 rounded-xl bg-tint-50/60 p-3 md:w-[220px] md:shrink-0 xl:w-auto xl:flex-1", hiddenOnPhone ? "hidden md:flex" : "flex")}>
      <h2 className="hidden items-center justify-between font-mono text-13 font-semibold md:flex">
        {title}
        <span aria-label={T.count(items.length)} className="rounded-full bg-card px-2 text-12 text-muted">{items.length}</span>
      </h2>
      {items.length === 0 ? <p className="rounded-lg border border-dashed border-hairline p-3 text-12 text-muted">{T.emptyColumn}</p> : <ul className="grid gap-2.5">{items.map((o) => <OfferCardRow key={o.id} o={o} />)}</ul>}
    </section>
  );
}

/** Причины отказов: считаем по самим приглашениям (отдельной выдачи в API нет). */
function Declines({ offers }: { offers: OfferForCompany[] }) {
  const rows = declineBreakdown(offers);
  if (rows.length === 0) return null;
  const total = rows.reduce((n, r) => n + r.count, 0);
  const top = rows[0];
  const topLabel = DECLINE_LABEL[top.reason] ?? top.reason;
  return (
    <section aria-label={T.declinesTitle} className="grid gap-5 rounded-2xl border border-hairline bg-card p-4 md:p-6 lg:grid-cols-2">
      <div className="grid content-start gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-mono text-20 font-semibold">{T.declinesTitle}</h2>
          <span className="font-mono text-12 text-muted">{T.declinesTotal(total)}</span>
        </div>
        <ul className="grid gap-2.5">
          {rows.map((r) => (
            <li key={r.reason} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 md:grid-cols-[140px_minmax(0,1fr)_44px]">
              <span className="text-14">{DECLINE_LABEL[r.reason] ?? r.reason}</span>
              <span className="font-mono text-13 font-semibold md:order-3 md:text-right">{r.pct}%</span>
              <span aria-hidden className="col-span-2 h-2.5 overflow-hidden rounded-full bg-tint-100 md:order-2 md:col-span-1">
                <span className="block h-full rounded-full bg-brand" style={{ width: `${r.pct}%` }} />
              </span>
            </li>
          ))}
        </ul>
      </div>
      <aside className="grid content-start gap-3 rounded-xl border border-tint-200 bg-tint-50 p-4">
        <SectionLabel className="inline-flex items-center gap-1.5"><Zap aria-hidden className="size-3.5" />{T.hintLabel}</SectionLabel>
        <p className="text-15"><b className="font-mono text-brand-fg">{topLabel} — {top.pct}%.</b> {T.hint[top.reason] ?? T.hintDefault}</p>
        <Link to="/employer/vacancies" className={cn(buttonVariants({ variant: "primary" }), "w-fit")}>{T.openVacancies}</Link>
      </aside>
    </section>
  );
}

/** Мои приглашения (экран E5): канбан по статусам, на телефоне — вкладки со счётчиками. */
export function EmployerOffers() {
  const q = useListOffersOffersGet();
  const [picked, setTab] = useState<BoardColumn | null>(null);
  const offers = q.data?.status === 200 ? q.data.data : [];
  const groups = groupByColumn(offers);
  const st = boardStats(offers);
  // Пока ничего не выбрано: первая непустая из «Отправлен» и «Интерес» (на телефоне иначе открылась бы пустая вкладка).
  const tab: BoardColumn = picked ?? (groups.sent.length === 0 && groups.interest.length > 0 ? "interest" : "sent");
  return (
    <main className="mx-auto flex w-full max-w-[1400px] flex-col gap-5 p-4 md:p-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="grid gap-1">
          <h1 className="font-mono text-28 font-semibold">{T.title}</h1>
          {q.isSuccess && <p className="text-14 text-muted">{T.subtitle(st.total)}</p>}
        </div>
        {q.isSuccess && offers.length > 0 && (
          <dl className="flex gap-6">
            {[
              [T.kpiViewed, st.viewedPct === null ? "—" : `${st.viewedPct}%`],
              [T.kpiAccepted, String(st.accepted)],
              [T.kpiHired, String(st.hired)],
            ].map(([k, v]) => (
              <div key={k} className="grid gap-0.5">
                <dt className="font-mono text-11 uppercase tracking-[.06em] text-muted">{k}</dt>
                <dd className="font-mono text-24 font-semibold text-brand-fg">{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </header>

      {q.isPending && <div role="status" aria-label="Загрузка" className="grid gap-3 md:grid-cols-3 xl:grid-cols-7">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-40" />)}</div>}
      {q.isError && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
      {q.isSuccess && offers.length === 0 && (
        <EmptyState
          title={T.empty}
          description={T.emptyHint}
          action={<Link to="/employer" className={buttonVariants({ variant: "primary" })}>{T.toSearch}</Link>}
        />
      )}
      {q.isSuccess && offers.length > 0 && (
        <>
          <div role="tablist" aria-label={T.tabs} className="-mx-4 flex gap-1 overflow-x-auto border-b border-hairline px-4 md:hidden">
            {BOARD_COLUMNS.map((id) => (
              <button
                key={id}
                role="tab"
                type="button"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className="-mb-px inline-flex min-h-11 shrink-0 items-center gap-2 border-b-2 border-transparent px-3 text-14 font-medium text-muted aria-selected:border-brand aria-selected:text-ink"
              >
                {T.columns[id]}
                <span className="rounded-full bg-tint-100 px-1.5 font-mono text-12 text-brand-fg">{groups[id].length}</span>
              </button>
            ))}
          </div>
          <div className="flex flex-col gap-3 md:flex-row md:overflow-x-auto md:pb-2">
            {BOARD_COLUMNS.map((id) => <Column key={id} id={id} items={groups[id]} hiddenOnPhone={tab !== id} />)}
          </div>
          <Declines offers={offers} />
        </>
      )}
    </main>
  );
}
