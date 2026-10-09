import { PAGE } from "@/shared/lib/page";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  useGetOfferOffersOfferIdGet,
  useSetOfferStatusOffersOfferIdStatusPost,
  useWithdrawOfferOffersOfferIdWithdrawPost,
} from "@/api/endpoints/offers/offers";
import { Button, ConstellationAvatar } from "@fsp/ui";
import type { OfferForCompany } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { FORMAT_LABEL, percent, rub } from "@/features/employer/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import { ContactsCard, invalidateOffers, MessageCard, Panel, StatusBadge, Timeline } from "./parts";
import { OfferDialog } from "./OfferDialog";
import { CAND_TEXT, CONTACTS_REVOKED_TEXT, dateOnly, DECLINE_LABEL, EMP_INT_TEXT as IT, offerErrorText } from "./text";

export { EmployerOffers } from "./EmployerBoard";

const NEXT: Record<string, { to: "interview" | "hired" | "not_hired"; label: string }[]> = {
  accepted: [{ to: "interview", label: "Пригласить на собеседование" }, { to: "not_hired", label: "Не нанимаем" }],
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
  const [inviteOpen, setInviteOpen] = useState(false);
  const isInterest = !!o && (o.status === "interest" || o.status === "interest_opened");
  return (
    <main className={PAGE.normal}>
      <Link to="/employer/offers" className="text-sm font-semibold text-brand-fg hover:underline">← Все приглашения</Link>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Приглашение не найден.</ErrorNote>}
      {o && (
        <>
          <header className="flex flex-wrap items-center gap-3">
            {o.candidate && <ConstellationAvatar seed={o.candidate.avatar_seed} size={56} />}
            <div className="flex min-w-0 flex-1 flex-col">
              <h1 className="break-words font-mono text-2xl font-semibold">{o.candidate ? displayPseudonym(o.candidate.pseudonym, o.candidate.primary_role) : "Кандидат удалил анкету"}</h1>
              {o.candidate && (
                <p className="text-[13px] text-muted">
                  {[o.candidate.grade && (GRADE_LABEL[o.candidate.grade] ?? o.candidate.grade), o.candidate.primary_role && roleLabel(o.candidate.primary_role)].filter(Boolean).join(" · ")}
                </p>
              )}
            </div>
            <StatusBadge status={o.status} />
          </header>

          <div className="grid items-start gap-4 lg:grid-cols-12">
            <div className="flex min-w-0 flex-col gap-4 lg:col-span-8">
              <Panel title={CAND_TEXT.conditions}>
                <p className="text-sm">{(o.vacancy as { title?: string } | null)?.title ?? (o as { title?: string | null }).title ?? "Приглашение"}{o.vacancy ? ` · ${o.vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}` : ""}</p>
                <p className="font-mono text-lg font-semibold">{rub(o.salary_from)} – {rub(o.salary_to)} <span className="font-sans text-sm font-normal text-muted">в месяц</span></p>
                {o.below_candidate_min && <p className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">Вилка ниже ожиданий кандидата.</p>}
                {o.match_snapshot && <p className="text-sm text-muted">Совпадение на момент приглашения: {percent(o.match_snapshot.score)}%</p>}
                {o.task && (
                  <p data-testid="offer-task" className="text-sm">
                    {o.task.answered_at ? `Задание «${o.task.title}» выполнено${o.task.score != null ? `, оценка ${percent(o.task.score)}%` : ""}` : `Задание «${o.task.title}» · ${o.task.minutes} мин · до ${dateOnly(o.task.deadline_at)}`}
                  </p>
                )}
                {o.message && <MessageCard label="Ваше сообщение" text={o.message} testId="offer-message" />}
                <p className="text-xs text-muted">{isInterest ? IT.interestSent : "Отправлен"} {dateOnly(o.created_at)}, ответить можно до {dateOnly(o.expires_at)}.</p>
                {isInterest && <p role="status" className="rounded-lg bg-tint-50 px-3 py-2 text-sm">{o.status === "interest_opened" ? IT.waitInvite : IT.waitOpen}</p>}
                {o.decline && (
                  <p className="rounded-lg bg-error-bg px-3 py-2 text-sm text-error">
                    Отказ: {DECLINE_LABEL[o.decline.reason] ?? o.decline.reason}{o.decline.comment ? `. ${o.decline.comment}` : ""}
                  </p>
                )}
                {err && <ErrorNote>{offerErrorText(err)}</ErrorNote>}
                <div className="flex flex-wrap gap-2">
                  {o.status === "interest_opened" && o.candidate && <Button onClick={() => setInviteOpen(true)}>{IT.invite}</Button>}
                  {(o.status === "sent" || o.status === "viewed" || isInterest) && (
                    <Button variant="outline" disabled={withdraw.isPending} onClick={() => withdraw.mutate({ offerId: o.id })}>{isInterest ? IT.withdrawInterest : "Отозвать приглашение"}</Button>
                  )}
                  {(NEXT[o.status] ?? []).map((n) => (
                    <Button key={n.to} variant={n.to === "not_hired" ? "outline" : "primary"} disabled={setStatus.isPending} onClick={() => setStatus.mutate({ offerId: o.id, data: { status: n.to } })}>{n.label}</Button>
                  ))}
                </div>
              </Panel>
            </div>

            <div className="flex min-w-0 flex-col gap-4 lg:col-span-4">
              {o.contacts_revoked_at && !o.contacts && (
                <p role="status" className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 text-warning-fg">{CONTACTS_REVOKED_TEXT}</p>
              )}
              {o.contacts && <ContactsCard title="Контакты кандидата" hint="Кандидат принял приглашение и раскрыл контакты. Он видит и ваши." contacts={o.contacts} testId="candidate-contacts" />}
              <Timeline offerId={o.id} />
            </div>
          </div>
          {o.candidate && o.status === "interest_opened" && (
            <OfferDialog
              open={inviteOpen}
              onOpenChange={setInviteOpen}
              mode="invite"
              interest={o}
              candidate={{ pseudoId: o.candidate.pseudo_id, pseudonym: o.candidate.pseudonym, salaryMin: o.candidate.salary_min ?? null }}
            />
          )}
        </>
      )}
    </main>
  );
}
