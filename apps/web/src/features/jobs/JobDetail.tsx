import { PAGE } from "@/shared/lib/page";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, cn, ErrorState, formatRubRange, SectionLabel, Skeleton, SkillChip } from "@fsp/ui";

import { useGetPublicVacancyVacanciesPublicVacancyIdGet } from "@/api/endpoints/vacancies/vacancies";
import { useApplyToVacancyVacanciesVacancyIdApplyPost } from "@/api/endpoints/vacancies/vacancies";
import { useMarkCandidateInterestCompaniesCompanyIdInterestPost, useRemoveCandidateInterestCompaniesCompanyIdInterestDelete } from "@/api/endpoints/search/search";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { roleLabel } from "@/features/profile/text";
import { useAuth } from "@/shared/lib/auth";
import { gradeSpan } from "./Jobs";
import { applyErrorText, isUnverified, JOBS_TEXT as T } from "./text";

/** Состояния кнопки отклика (макет J1): не вошёл, не кандидат, email не подтверждён, отправлено. */
function ApplyBox({ vacancyId }: { vacancyId: string }) {
  const { status, role } = useAuth();
  const loc = useLocation();
  const qc = useQueryClient();
  const [message, setMessage] = useState("");
  const apply = useApplyToVacancyVacanciesVacancyIdApplyPost({
    mutation: { onSuccess: () => void qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/candidates/me") || String(q.queryKey[0]).startsWith("/offers") }) },
  });
  if (status !== "authenticated") {
    return (
      <section className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4">
        <p className="text-14 text-muted">{T.loginHint}</p>
        <Link to="/login" state={{ from: loc.pathname }} className="inline-flex h-12 items-center justify-center rounded-lg bg-brand px-5 font-semibold text-on-brand">
          {T.loginApply}
        </Link>
      </section>
    );
  }
  if (role !== "candidate") return <p className="rounded-xl border border-hairline bg-card p-4 text-14 text-muted">{T.employerHint}</p>;
  if (apply.isSuccess && apply.data.status === 201) {
    return (
      <section role="status" className="flex flex-col gap-2 rounded-xl border border-brand-mid bg-tint-50 p-4">
        <h2 className="font-mono text-16 font-semibold">{T.sentTitle}</h2>
        <p className="text-14">{T.sentHint}</p>
        <Link to="/me/responses" className="text-14 font-semibold text-brand-fg hover:underline">{T.toResponses}</Link>
      </section>
    );
  }
  const unverified = isUnverified(apply.error);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        apply.mutate({ vacancyId, data: { message: message.trim() || null } });
      }}
      className="flex flex-col gap-3"
    >
      <label className="flex flex-col gap-1 text-13 font-semibold">
        {T.messageLabel}
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} rows={4} placeholder={T.messagePlaceholder} className={cn(fieldClass, "h-auto py-2 font-normal")} />
      </label>
      <p className="text-12 text-muted">{T.contactsNote}</p>
      {unverified ? (
        <section role="alert" className="flex flex-col gap-2 rounded-xl border border-warning-border bg-warning-bg p-4 text-warning-fg">
          <h2 className="font-mono text-16 font-semibold">{T.unverifiedTitle}</h2>
          <p className="text-14">{T.unverifiedHint}</p>
          <Link to="/verify-email" className="text-14 font-semibold underline">{T.unverifiedAction}</Link>
        </section>
      ) : (
        apply.isError && <ErrorNote>{applyErrorText(apply.error)}</ErrorNote>
      )}
      <Button type="submit" size="lg" loading={apply.isPending} disabled={unverified}>{apply.isPending ? T.sending : T.apply}</Button>
    </form>
  );
}

/** Встречный сигнал кандидата (E33-6): «интересна компания». Только для кандидата; снимается. */
function CompanyInterest({ companyId }: { companyId: string }) {
  const { status, role } = useAuth();
  const [marked, setMarked] = useState(false);
  const mark = useMarkCandidateInterestCompaniesCompanyIdInterestPost({ mutation: { onSuccess: () => setMarked(true) } });
  const unmark = useRemoveCandidateInterestCompaniesCompanyIdInterestDelete({ mutation: { onSuccess: () => setMarked(false) } });
  if (status !== "authenticated" || role !== "candidate") return null;
  const err = mark.isError || unmark.isError;
  return (
    <section aria-label={T.companyInterest} className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4">
      {marked ? (
        <>
          <p role="status" className="text-14">{T.companyInterestOn}</p>
          <Button variant="outline" loading={unmark.isPending} onClick={() => unmark.mutate({ companyId })}>{T.companyInterestOff}</Button>
        </>
      ) : (
        <>
          <p className="text-13 text-muted">{T.companyInterestHint}</p>
          <Button variant="outline" loading={mark.isPending} onClick={() => mark.mutate({ companyId })}>{T.companyInterest}</Button>
        </>
      )}
      {err && <ErrorNote>{T.companyInterestError}</ErrorNote>}
    </section>
  );
}

/** Вакансия (J1, /jobs/:id). «Назад к списку» возвращает на тот же поиск: фильтры лежат в URL списка. */
export default function JobDetail() {
  const { id = "" } = useParams();
  const loc = useLocation();
  const search = (loc.state as { search?: string } | null)?.search ?? "";
  const q = useGetPublicVacancyVacanciesPublicVacancyIdGet(id, { query: { retry: false } });
  const v = q.data?.status === 200 ? q.data.data : undefined;
  return (
    <div className={PAGE.narrow}>
      <Link to={`/jobs${search}`} className="text-sm font-semibold text-brand-fg hover:underline">← {T.back}</Link>
      {q.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-64" />}
      {q.isError && <ErrorState title={T.notFound} onRetry={() => void q.refetch()} />}
      {v && (
        <>
          <header className="flex flex-col gap-1">
            <h1 className="break-words font-mono text-24 font-semibold">{v.title}</h1>
            <p className="text-13 text-muted">
              {[v.company.name, v.city, v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ").toLowerCase(), T.employment[v.employment_type]].filter(Boolean).join(" · ")}
            </p>
          </header>
          <div>
            <SectionLabel>{T.range}</SectionLabel>
            <p className="font-mono text-24 font-semibold text-brand-deep dark:text-brand-mid">{formatRubRange(v.salary_from, v.salary_to)}</p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <span className="rounded-md bg-brand px-2 py-0.5 font-mono text-12 font-semibold text-on-brand">{roleLabel(v.role)} · {gradeSpan(v)}</span>
            {v.skills.map((s) => (
              <SkillChip key={s.slug} name={s.slug} variant="claimed" title={s.required ? T.required : undefined} />
            ))}
          </div>
          {v.description && (
            <section className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-4">
              <SectionLabel>{T.description}</SectionLabel>
              <p className="whitespace-pre-wrap break-words text-14">{v.description}</p>
            </section>
          )}
          <ApplyBox vacancyId={v.id} />
          <CompanyInterest companyId={v.company.id} />
        </>
      )}
    </div>
  );
}
