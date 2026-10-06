import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, ConstellationAvatar, EmptyState, ErrorState, MatchRing, Skeleton, StatusBadge, buttonVariants, type OfferStatus } from "@fsp/ui";

import { useListOffersOffersGet, useSetOfferStatusOffersOfferIdStatusPost } from "@/api/endpoints/offers/offers";
import type { OfferForCompany } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { percent } from "@/features/employer/text";
import { invalidateOffers } from "@/features/offers/parts";
import { dateOnly } from "@/features/offers/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { countBy, empTabOf, filterBy } from "./response-model";
import { RESP_TEXT as T } from "./text";
import { FilterTabs } from "./Tabs";

function Row({ o }: { o: OfferForCompany }) {
  const qc = useQueryClient();
  const set = useSetOfferStatusOffersOfferIdStatusPost({ mutation: { onSuccess: () => void invalidateOffers(qc) } });
  const c = o.candidate;
  const pending = o.status === "sent" || o.status === "viewed";
  const invited = o.status === "interview" || o.status === "accepted";
  const sub = c ? [c.primary_role && roleLabel(c.primary_role), c.grade && (GRADE_LABEL[c.grade] ?? c.grade)].filter(Boolean).join(" · ") : "";
  return (
    <li className="grid gap-3 rounded-xl border border-hairline bg-card p-3 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_auto_auto_auto] md:items-center">
      <Link to={`/employer/offers/${o.id}`} className="flex min-w-0 items-center gap-2.5 hover:underline">
        {c && <ConstellationAvatar seed={c.avatar_seed} size={40} />}
        <span className="grid min-w-0">
          <span className="break-words font-mono text-14 font-semibold">{c?.pseudonym ?? T.deleted}</span>
          <span className="text-12 text-muted">{[sub, dateOnly(o.created_at)].filter(Boolean).join(" · ")}</span>
        </span>
      </Link>
      <span className="break-words text-14">{o.vacancy?.title ?? o.title}</span>
      <StatusBadge status={o.status as OfferStatus} />
      {o.match_snapshot ? <MatchRing value={percent(o.match_snapshot.score)} size={44} /> : <span aria-hidden />}
      <div className="flex flex-wrap items-center gap-2">
        {pending && (
          <>
            <Button size="sm" loading={set.isPending} onClick={() => set.mutate({ offerId: o.id, data: { status: "interview" } })}>{T.invite}</Button>
            <Button size="sm" variant="outline" disabled={set.isPending} onClick={() => set.mutate({ offerId: o.id, data: { status: "not_hired" } })}>{T.reject}</Button>
          </>
        )}
        {invited && (
          <Link to={`/employer/offers/${o.id}`} className={buttonVariants({ size: "sm" })}>{T.write}</Link>
        )}
      </div>
      {set.isError && (
        <div className="md:col-span-full">
          <ErrorNote>{T.actionError}</ErrorNote>
        </div>
      )}
    </li>
  );
}

/** Отклики на вакансии (R1, работодатель): те же офферы с initiator = candidate. */
export default function EmployerResponses() {
  const q = useListOffersOffersGet({ initiator: "candidate" });
  const all = (q.data?.status === 200 ? q.data.data : []) as OfferForCompany[];
  const sorted = [...all].sort((a, b) => b.created_at.localeCompare(a.created_at));
  const [tab, setTab] = useState("all");
  const shown = filterBy(sorted, tab, empTabOf);
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-4 md:p-6">
      <header className="flex flex-col gap-1">
        <h1 className="font-mono text-24 font-semibold">{T.empTitle}</h1>
        <p className="max-w-2xl text-14 text-muted">{T.empLead}</p>
      </header>
      {q.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-48" />}
      {q.isError && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
      {q.isSuccess && all.length === 0 && <EmptyState title={T.empEmpty} description={T.empEmptyHint} />}
      {all.length > 0 && (
        <>
          <FilterTabs label="Фильтр откликов" tabs={T.empTabs} value={tab} counts={countBy(sorted, empTabOf)} onChange={setTab} />
          <ul className="grid gap-2.5">{shown.map((o) => <Row key={o.id} o={o} />)}</ul>
        </>
      )}
    </main>
  );
}
