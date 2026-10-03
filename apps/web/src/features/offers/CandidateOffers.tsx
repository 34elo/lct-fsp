import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  useAcceptOfferOffersOfferIdAcceptPost,
  useDeclineOfferOffersOfferIdDeclinePost,
  useGetOfferOffersOfferIdGet,
  useMyOffersCandidatesMeOffersGet,
} from "@/api/endpoints/offers/offers";
import { DeclineReason, type OfferForCandidate } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL, percent, rub, splitExplanation } from "@/features/employer/text";
import { GRADE_LABEL } from "@/features/profile/text";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/button";
import { Conversation, invalidateOffers, Panel, StatusBadge, Timeline } from "./parts";
import { ACTIVE_STATUSES, daysLeft, dateOnly, DECLINE_LABEL, offerErrorText } from "./text";

function Row({ o }: { o: OfferForCandidate }) {
  const active = o.status === "sent" || o.status === "viewed";
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="break-words font-mono text-[17px] font-semibold">{o.company.name}</h2>
          <p className="text-[13px] text-muted">
            {o.company.responsibility_score != null ? `${o.company.responsibility_score.toFixed(1)} / 5 ответственность` : "Рейтинг ещё не сформирован"}
          </p>
        </div>
        <StatusBadge status={o.status} />
      </div>
      <p className="text-xs uppercase tracking-wide text-muted">Вилка в месяц</p>
      <p className="font-mono text-xl font-semibold">{rub(o.salary_from)} – {rub(o.salary_to)}</p>
      <p className="text-sm">{o.vacancy.title} · {o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}{o.match_snapshot ? ` · ${percent(o.match_snapshot.score)}%` : ""}</p>
      {o.below_candidate_min && <p className="rounded-lg bg-warning-bg px-3 py-1.5 text-sm text-warning-fg">Ниже ваших ожиданий</p>}
      <p className="text-xs text-muted">{active ? `Ответить до ${dateOnly(o.expires_at)} · осталось ${daysLeft(o.expires_at)} дн.` : `Получен ${dateOnly(o.created_at)}`}</p>
      <Link to={`/me/offers/${o.id}`} className="inline-flex h-11 items-center justify-center rounded-lg bg-brand px-4 font-semibold text-on-brand hover:bg-brand-deep md:self-start">Открыть оффер</Link>
    </li>
  );
}

/** Офферы кандидата (M2): активные сверху, прошлые ниже. */
export function CandidateOffers() {
  const q = useMyOffersCandidatesMeOffersGet();
  const all = q.data?.status === 200 ? q.data.data : [];
  const active = all.filter((o) => ACTIVE_STATUSES.includes(o.status));
  const past = all.filter((o) => !ACTIVE_STATUSES.includes(o.status));
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <h1 className="font-mono text-2xl font-semibold">Офферы</h1>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Не удалось загрузить офферы.</ErrorNote>}
      {q.isSuccess && all.length === 0 && <p className="rounded-xl border border-hairline bg-card p-5 text-sm">Офферов пока нет. Они приходят сюда и в Telegram, когда компании находят ваш профиль.</p>}
      <ul className="flex flex-col gap-3">{active.map((o) => <Row key={o.id} o={o} />)}</ul>
      {past.length > 0 && (
        <>
          <h2 className="font-mono text-[17px] font-semibold text-muted">Прошлые офферы</h2>
          <ul className="flex flex-col gap-3">{past.map((o) => <Row key={o.id} o={o} />)}</ul>
        </>
      )}
    </main>
  );
}

export function CandidateOfferDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useGetOfferOffersOfferIdGet(id, { query: { retry: false } });
  const o = q.data?.status === 200 ? (q.data.data as OfferForCandidate) : null;
  const done = () => void invalidateOffers(qc);
  const accept = useAcceptOfferOffersOfferIdAcceptPost({ mutation: { onSuccess: done } });
  const decline = useDeclineOfferOffersOfferIdDeclinePost({ mutation: { onSuccess: () => { setSheet(false); done(); } } });
  const [sheet, setSheet] = useState(false);
  const [reason, setReason] = useState<DeclineReason | null>(null);
  const [comment, setComment] = useState("");
  const answerable = o && (o.status === "sent" || o.status === "viewed");
  const ex = o?.match_snapshot ? splitExplanation(o.match_snapshot.explanation) : null;
  const err = accept.error ?? decline.error;
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <Link to="/me/offers" className="text-sm font-semibold text-brand-fg hover:underline">← Все офферы</Link>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Оффер не найден.</ErrorNote>}
      {o && (
        <>
          <section className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4 md:p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="break-words font-mono text-2xl font-semibold">{o.company.name}</h1>
                <p className="text-sm text-muted">
                  {o.vacancy.title} · {GRADE_LABEL[o.vacancy.grade_min]}–{GRADE_LABEL[o.vacancy.grade_max]} · {o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}
                </p>
              </div>
              <StatusBadge status={o.status} />
            </div>
            <p className="text-xs uppercase tracking-wide text-muted">Вилка в месяц</p>
            <p className="font-mono text-3xl font-semibold">{rub(o.salary_from)} – {rub(o.salary_to)}</p>
            {o.below_candidate_min && <p className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">Ниже ваших ожиданий.</p>}
            {o.message && (<><p className="text-xs uppercase tracking-wide text-muted">Сообщение компании</p><p className="whitespace-pre-wrap break-words rounded-lg bg-tint-50 p-3 text-sm">{o.message}</p></>)}
            <p className="text-xs text-muted">{answerable ? `Ответить до ${dateOnly(o.expires_at)} · осталось ${daysLeft(o.expires_at)} дн.` : `Получен ${dateOnly(o.created_at)}`}</p>
            {o.decline && <p className="text-sm text-muted">Ваш отказ: {DECLINE_LABEL[o.decline.reason] ?? o.decline.reason}</p>}
            {(o.status === "accepted" || o.status === "interview") && (
              <p role="status" className="rounded-lg bg-success-bg px-3 py-2 text-sm text-success">
                Вы приняли оффер. Компания теперь видит ваши контакты и свяжется с вами; пока можно общаться здесь.
              </p>
            )}
            {err && <ErrorNote>{offerErrorText(err)}</ErrorNote>}
            {answerable && !sheet && (
              <div className="flex flex-wrap gap-2">
                <Button size="lg" disabled={accept.isPending} onClick={() => accept.mutate({ offerId: o.id })}>Принять</Button>
                <Button size="lg" variant="outline" onClick={() => setSheet(true)}>Не подходит</Button>
              </div>
            )}
            {answerable && sheet && (
              <div role="group" aria-label="Причина отказа" className="flex flex-col gap-2 rounded-xl border border-hairline p-3">
                <p className="font-semibold">Почему не подходит?</p>
                <p className="text-xs text-muted">Компания увидит причину без имени и контактов.</p>
                <div className="flex flex-wrap gap-2">
                  {Object.values(DeclineReason).map((r) => (
                    <button key={r} type="button" aria-pressed={reason === r} onClick={() => setReason(r)} className={cn("h-10 rounded-lg px-3 text-sm font-semibold", reason === r ? "bg-brand text-on-brand" : "border border-hairline hover:bg-tint-50")}>
                      {DECLINE_LABEL[r]}
                    </button>
                  ))}
                </div>
                <label className="sr-only" htmlFor="decline-comment">Комментарий</label>
                <textarea id="decline-comment" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={1000} rows={2} placeholder="Комментарий (необязательно)" className={cn(fieldClass, "h-auto py-2")} />
                <div className="flex gap-2">
                  <Button disabled={!reason || decline.isPending} onClick={() => reason && decline.mutate({ offerId: o.id, data: { reason, comment: comment.trim() || null } })}>Отклонить оффер</Button>
                  <Button variant="ghost" onClick={() => setSheet(false)}>Назад</Button>
                </div>
              </div>
            )}
          </section>
          {ex && (ex.pluses.length > 0 || ex.others.length > 0) && (
            <Panel title="Почему вы подходите">
              <ul className="flex flex-col gap-1.5 text-sm">
                {ex.pluses.map((i, n) => <li key={`p${n}`} className="flex gap-2"><span aria-hidden className="text-success">+</span>{i.text}</li>)}
                {ex.others.map((i, n) => <li key={`w${n}`} className="flex gap-2 text-muted"><span aria-hidden className="text-warning">!</span>{i.text}</li>)}
              </ul>
            </Panel>
          )}
          <Conversation offerId={o.id} side="candidate" canWrite={ACTIVE_STATUSES.includes(o.status)} />
          <Timeline offerId={o.id} />
        </>
      )}
    </main>
  );
}
