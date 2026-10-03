import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  useGetOfferOffersOfferIdGet,
  useListOffersOffersGet,
  useSetOfferStatusOffersOfferIdStatusPost,
  useWithdrawOfferOffersOfferIdWithdrawPost,
} from "@/api/endpoints/offers/offers";
import type { OfferForCompany } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { FORMAT_LABEL, percent, rub } from "@/features/employer/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { ConstellationAvatar } from "@/shared/brand";
import { Button } from "@/shared/ui/button";
import { Conversation, invalidateOffers, Panel, StatusBadge, Timeline } from "./parts";
import { dateOnly, DECLINE_LABEL, offerErrorText } from "./text";

const FILTERS: { id: string; label: string; match: (s: string) => boolean }[] = [
  { id: "all", label: "Все", match: () => true },
  { id: "open", label: "Ждут ответа", match: (s) => s === "sent" || s === "viewed" },
  { id: "work", label: "В работе", match: (s) => ["accepted", "interview"].includes(s) },
  { id: "done", label: "Закрытые", match: (s) => ["hired", "not_hired", "declined", "expired", "withdrawn"].includes(s) },
];

function Row({ o }: { o: OfferForCompany }) {
  const c = o.candidate;
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4 shadow-card">
      <div className="flex items-start gap-3">
        {c && <ConstellationAvatar seed={c.avatar_seed} size={44} />}
        <div className="flex min-w-0 flex-1 flex-col">
          <h2 className="break-words font-mono text-[17px] font-semibold">{c?.pseudonym ?? "Кандидат удалил анкету"}</h2>
          <p className="text-[13px] text-muted">{o.vacancy.title}</p>
        </div>
        <StatusBadge status={o.status} />
      </div>
      <p className="font-mono text-sm font-semibold">{rub(o.salary_from)} – {rub(o.salary_to)}</p>
      <p className="flex flex-wrap gap-x-3 text-xs text-muted">
        <span>Отправлен {dateOnly(o.created_at)}</span>
        {o.decline && <span>Причина: {DECLINE_LABEL[o.decline.reason] ?? o.decline.reason}</span>}
        {o.awaiting_reply_from === "company" && <b className="text-brand-fg">Ждёт вашего ответа</b>}
      </p>
      <Link to={`/employer/offers/${o.id}`} className="inline-flex h-9 items-center self-start rounded-lg border border-brand-fg px-3 text-sm font-semibold text-brand-fg hover:bg-tint-50">Открыть</Link>
    </li>
  );
}

/** Мои офферы (экран E5, упрощённо: список со статусами и фильтрами). */
export function EmployerOffers() {
  const q = useListOffersOffersGet();
  const [f, setF] = useState("all");
  const list = (q.data?.status === 200 ? q.data.data : []).filter((o) => FILTERS.find((x) => x.id === f)!.match(o.status));
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 md:p-6">
      <h1 className="font-mono text-2xl font-semibold">Мои офферы</h1>
      <div role="tablist" aria-label="Статусы" className="flex flex-wrap gap-2">
        {FILTERS.map((x) => (
          <button key={x.id} role="tab" aria-selected={f === x.id} onClick={() => setF(x.id)} className={`h-9 rounded-lg px-3 text-sm font-semibold ${f === x.id ? "bg-brand text-on-brand" : "border border-hairline hover:bg-tint-50"}`}>
            {x.label}
          </button>
        ))}
      </div>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Не удалось загрузить офферы.</ErrorNote>}
      {q.isSuccess && list.length === 0 && (
        <p className="rounded-xl border border-hairline bg-card p-5 text-sm">
          Офферов здесь пока нет. Найдите кандидата в <Link className="font-semibold text-brand-fg" to="/employer/search">поиске</Link> и отправьте первый.
        </p>
      )}
      <ul className="grid gap-3 md:grid-cols-2">{list.map((o) => <Row key={o.id} o={o} />)}</ul>
    </main>
  );
}

const NEXT: Record<string, { to: "interview" | "hired" | "not_hired"; label: string }[]> = {
  accepted: [{ to: "interview", label: "Пригласить на интервью" }, { to: "not_hired", label: "Не нанимаем" }],
  interview: [{ to: "hired", label: "Нанят" }, { to: "not_hired", label: "Не нанимаем" }],
};

export function EmployerOfferDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useGetOfferOffersOfferIdGet(id, { query: { retry: false } });
  const o = q.data?.status === 200 ? (q.data.data as OfferForCompany) : null;
  const done = () => void invalidateOffers(qc);
  const withdraw = useWithdrawOfferOffersOfferIdWithdrawPost({ mutation: { onSuccess: done } });
  const setStatus = useSetOfferStatusOffersOfferIdStatusPost({ mutation: { onSuccess: done } });
  const err = withdraw.error ?? setStatus.error;
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <Link to="/employer/offers" className="text-sm font-semibold text-brand-fg hover:underline">← Все офферы</Link>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Оффер не найден.</ErrorNote>}
      {o && (
        <>
          <section className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4 md:p-5">
            <div className="flex flex-wrap items-center gap-3">
              {o.candidate && <ConstellationAvatar seed={o.candidate.avatar_seed} size={56} />}
              <div className="flex min-w-0 flex-1 flex-col">
                <h1 className="break-words font-mono text-2xl font-semibold">{o.candidate?.pseudonym ?? "Кандидат удалил анкету"}</h1>
                {o.candidate && (
                  <p className="text-[13px] text-muted">
                    {[o.candidate.grade && (GRADE_LABEL[o.candidate.grade] ?? o.candidate.grade), o.candidate.primary_role && roleLabel(o.candidate.primary_role)].filter(Boolean).join(" · ")}
                  </p>
                )}
              </div>
              <StatusBadge status={o.status} />
            </div>
            <p className="text-sm">{o.vacancy.title} · {o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}</p>
            <p className="font-mono text-lg font-semibold">{rub(o.salary_from)} – {rub(o.salary_to)} <span className="font-sans text-sm font-normal text-muted">в месяц</span></p>
            {o.below_candidate_min && <p className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">Вилка ниже ожиданий кандидата.</p>}
            {o.match_snapshot && <p className="text-sm text-muted">Совпадение на момент оффера: {percent(o.match_snapshot.score)}%</p>}
            {o.message && <p className="whitespace-pre-wrap break-words rounded-lg bg-tint-50 p-3 text-sm">{o.message}</p>}
            <p className="text-xs text-muted">Отправлен {dateOnly(o.created_at)}, ответить можно до {dateOnly(o.expires_at)}.</p>
            {o.decline && (
              <p className="rounded-lg bg-error-bg px-3 py-2 text-sm text-error">
                Отказ: {DECLINE_LABEL[o.decline.reason] ?? o.decline.reason}{o.decline.comment ? `. ${o.decline.comment}` : ""}
              </p>
            )}
            {err && <ErrorNote>{offerErrorText(err)}</ErrorNote>}
            <div className="flex flex-wrap gap-2">
              {(o.status === "sent" || o.status === "viewed") && (
                <Button variant="outline" disabled={withdraw.isPending} onClick={() => withdraw.mutate({ offerId: o.id })}>Отозвать оффер</Button>
              )}
              {(NEXT[o.status] ?? []).map((n) => (
                <Button key={n.to} variant={n.to === "not_hired" ? "outline" : "primary"} disabled={setStatus.isPending} onClick={() => setStatus.mutate({ offerId: o.id, data: { status: n.to } })}>{n.label}</Button>
              ))}
            </div>
          </section>

          {o.contacts && (
            <Panel title="Контакты кандидата">
              <p className="text-xs text-muted">Кандидат принял оффер и раскрыл контакты.</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                <dt className="text-muted">Имя</dt><dd>{o.contacts.name}</dd>
                {o.contacts.email && (<><dt className="text-muted">Почта</dt><dd className="break-all"><a className="text-brand-fg" href={`mailto:${o.contacts.email}`}>{o.contacts.email}</a></dd></>)}
                {o.contacts.telegram && (<><dt className="text-muted">Telegram</dt><dd>{o.contacts.telegram}</dd></>)}
                {o.contacts.phone && (<><dt className="text-muted">Телефон</dt><dd>{o.contacts.phone}</dd></>)}
              </dl>
            </Panel>
          )}
          <Conversation offerId={o.id} side="company" canWrite={["sent", "viewed", "accepted", "interview"].includes(o.status)} />
          <Timeline offerId={o.id} />
        </>
      )}
    </main>
  );
}
