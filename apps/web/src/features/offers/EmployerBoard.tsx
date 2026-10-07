import { Link } from "react-router-dom";

import { buttonVariants, cn, EmptyState, ErrorState, formatRubRangeShort, GradeTag, H1, Lbl, Num, Panel, Skeleton, StatusBadge, type OfferStatus } from "@fsp/ui";

import { useListMessagesOffersOfferIdMessagesGet, useListOffersOffersGet } from "@/api/endpoints/offers/offers";
import type { OfferForCompany } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { GRADE_LABEL } from "@/features/profile/text";
import { funnelOf, funnelSpanDays, lastActive, sortOffers } from "./offer-model";
import { BOARD_TEXT as T } from "./text";

const COLS = "md:grid-cols-[1.1fr_0.6fr_1.1fr_1fr_1.2fr]";
const shortDate = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });

/** Вилка: обе границы — «150–220 тыс. ₽», только нижняя — «от 220 000 ₽». */
const salary = (o: OfferForCompany) => (o.salary_to > o.salary_from ? formatRubRangeShort(o.salary_from, o.salary_to) : T.from(o.salary_from));

function note(o: OfferForCompany): string {
  if (o.status === "interest") return T.waiting;
  if (o.status === "interest_opened") return shortDate(o.interest_opened_at ?? o.created_at);
  if (o.contacts) return T.contactsOpen;
  if (o.status === "sent" || o.status === "viewed") return [o.task ? T.task : null, T.contactsHidden].filter(Boolean).join(" · ");
  return shortDate(o.created_at);
}

function Name({ o }: { o: OfferForCompany }) {
  return <span className="break-words font-mono text-14 font-semibold">{o.candidate?.pseudonym ?? T.deleted}</span>;
}

function grade(o: OfferForCompany) {
  const g = o.candidate?.grade;
  return g ? (GRADE_LABEL[g] ?? g) : null;
}

function Funnel({ offers }: { offers: OfferForCompany[] }) {
  const f = funnelOf(offers);
  const days = funnelSpanDays(offers, Date.now());
  const steps = [
    [f.interest, T.funnel.interest],
    [f.opened, T.funnel.opened],
    [f.invited, T.funnel.invited],
    [f.accepted, T.funnel.accepted],
  ] as const;
  return (
    <Panel aria-label={T.funnelTitle} className="flex flex-col gap-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="font-mono text-16 font-semibold">{T.funnelTitle}</h2>
        <Lbl>{T.days(days)}</Lbl>
      </div>
      <ol className="m-0 mt-2 grid list-none grid-cols-4 border-t-2 border-brand p-0">
        {steps.map(([n, label], i) => (
          <li key={label} className="relative pr-2 pt-3.5 text-12">
            <span aria-hidden className={cn("absolute -top-[9px] left-0 size-3.5 rounded-full border-[3px] border-card ring-1", i === 2 ? "bg-signal ring-signal" : "bg-brand ring-brand")} />
            <Num className="block text-20 font-semibold">{n}</Num>
            <Lbl>{label}</Lbl>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function OffersTable({ offers }: { offers: OfferForCompany[] }) {
  return (
    <Panel className="overflow-hidden p-0" aria-label={T.listTitle}>
      <div className="flex items-baseline justify-between px-4 pb-2.5 pt-3.5">
        <h2 className="font-mono text-16 font-semibold">{T.listTitle}</h2>
        <Lbl>{offers.length}</Lbl>
      </div>
      <div className={cn("hidden min-h-9 items-center gap-3 px-4 md:grid", COLS)} aria-hidden>
        {[T.colCandidate, T.colGrade, T.colStatus, T.colSalary, T.colNote].map((h) => (
          <Lbl key={h}>{h}</Lbl>
        ))}
      </div>
      <ul className="m-0 hidden list-none p-0 md:block">
        {offers.map((o) => (
          <li key={o.id} className="border-t border-hairline">
            <Link
              to={`/employer/offers/${o.id}`}
              data-testid="offer-row"
              aria-label={`${o.candidate?.pseudonym ?? T.deleted}, ${T.open}`}
              className={cn("grid items-center gap-3 px-4 py-3 hover:bg-tint-50 focus-visible:outline-2 focus-visible:outline-brand", COLS)}
            >
              <Name o={o} />
              <span className="justify-self-start">{grade(o) && <GradeTag>{grade(o)}</GradeTag>}</span>
              <span className="justify-self-start"><StatusBadge status={o.status as OfferStatus} /></span>
              <Num className="whitespace-nowrap text-14">{salary(o)}</Num>
              <span className="text-13 text-muted">{note(o)}</span>
            </Link>
          </li>
        ))}
      </ul>
      <ul className="m-0 grid list-none gap-2 p-2 md:hidden">
        {offers.map((o) => (
          <li key={o.id}>
            <Link to={`/employer/offers/${o.id}`} aria-label={`${o.candidate?.pseudonym ?? T.deleted}, ${T.open}`} className="grid gap-2 rounded-xl border border-hairline bg-card p-3 shadow-xs hover:border-brand-mid">
              <span className="flex items-center justify-between gap-2"><Name o={o} /><StatusBadge status={o.status as OfferStatus} /></span>
              <span className="flex items-center justify-between gap-2"><Num className="text-14">{salary(o)}</Num><span className="text-12 text-muted">{note(o)}</span></span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/** Последняя переписка по активному приглашению: быстрый «Ответить» без поиска по списку. */
function Latest({ offer }: { offer: OfferForCompany }) {
  const q = useListMessagesOffersOfferIdMessagesGet(offer.id, { query: { refetchInterval: 30_000 } });
  const msgs = q.data?.status === 200 ? q.data.data : [];
  const last = [...msgs].reverse().find((m) => m.author_side !== "company") ?? msgs[msgs.length - 1];
  return (
    <Panel className="flex flex-col gap-2.5" aria-label={T.latestTitle}>
      <div className="flex items-center justify-between gap-2">
        <Name o={offer} />
        <StatusBadge status={offer.status as OfferStatus} />
      </div>
      <p className="m-0 whitespace-pre-wrap break-words rounded-lg border border-tint-200 bg-tint-50 p-3 text-14">{last?.text ?? T.noMessages}</p>
      <Link to={`/employer/offers/${offer.id}`} className={cn(buttonVariants({ size: "lg" }), "w-full")}>{T.reply}</Link>
    </Panel>
  );
}

function Responses({ items }: { items: OfferForCompany[] }) {
  if (items.length === 0) return null;
  return (
    <Panel aria-label={T.responsesTitle} className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2 pb-1.5">
        <h2 className="font-mono text-16 font-semibold">{T.responsesTitle}</h2>
        <Lbl>{items.length}</Lbl>
      </div>
      {items.slice(0, 5).map((o) => (
        <Link key={o.id} to={`/employer/offers/${o.id}`} className="flex items-center justify-between gap-2 border-t border-hairline py-2.5 first:border-t-0 hover:underline">
          <Name o={o} />
          {grade(o) && <GradeTag>{grade(o)}</GradeTag>}
        </Link>
      ))}
      <Link to="/employer/responses" className="pt-2 text-14 font-semibold text-brand-fg hover:underline">{T.allResponses}</Link>
    </Panel>
  );
}

function Loading() {
  return (
    <div aria-hidden data-testid="offers-loading" className="grid gap-3 md:grid-cols-3">
      {[0, 1, 2].map((i) => (
        <Panel key={i} className="flex flex-col gap-2.5">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[70%]" />
        </Panel>
      ))}
    </div>
  );
}

/** Приглашения работодателя `/employer/offers` (E38-13, бриф §6.13): воронка, таблица предложений, последняя переписка, отклики. */
export function EmployerOffers() {
  const q = useListOffersOffersGet();
  const all = q.data?.status === 200 ? (q.data.data as OfferForCompany[]) : [];
  const offers = sortOffers(all.filter((o) => o.initiator !== "candidate"));
  const responses = all.filter((o) => o.initiator === "candidate");
  const active = lastActive(offers);
  const code = q.error instanceof ApiError ? T.code(q.error.status) : undefined;
  const empty = q.isSuccess && all.length === 0;
  return (
    <main className="mx-auto flex w-full max-w-[1328px] flex-col gap-4 px-4 py-4 md:px-6 md:py-6">
      {q.isPending ? <Skeleton className="h-7 w-56" /> : <H1 className="text-[22px] md:text-[26px]">{T.title}</H1>}
      {q.isPending && <Loading />}
      {q.isError && <ErrorState title={T.loadError} code={code} onRetry={() => void q.refetch()} />}
      {empty && (
        <EmptyState
          title={T.empty}
          action={<Link to="/employer" className={buttonVariants({ size: "lg" })}>{T.toSearch}</Link>}
        />
      )}
      {q.isSuccess && !empty && (
        <div className="grid items-start gap-4 lg:grid-cols-12">
          <div className="order-2 flex min-w-0 flex-col gap-4 lg:order-1 lg:col-span-8">
            {offers.length > 0 && <Funnel offers={offers} />}
            {offers.length > 0 && <OffersTable offers={offers} />}
          </div>
          <div className="order-1 flex min-w-0 flex-col gap-4 lg:order-2 lg:col-span-4">
            {active && <Latest offer={active} />}
            <Responses items={responses} />
          </div>
        </div>
      )}
    </main>
  );
}
