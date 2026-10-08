import { PAGE } from "@/shared/lib/page";
import { Link } from "react-router-dom";

import { Badge, EmptyState, ErrorState, SectionLabel, Skeleton, formatRubRange } from "@fsp/ui";

import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { EMPLOYMENT_LABEL, FORMAT_LABEL, VACANCY_STATUS_LABEL } from "./text";

const linkBtn =
  "inline-flex h-10 items-center justify-center rounded-lg px-4 text-14 font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

/** Свои вакансии (экран E3, список): строка на вакансию, оттуда идём в подборку. */
export default function Vacancies() {
  const q = useListVacanciesVacanciesGet();
  const list = q.data?.status === 200 ? q.data.data : [];
  return (
    <main className={PAGE.normal}>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="grid gap-1">
          <SectionLabel>Работодатель</SectionLabel>
          <h1 className="font-mono text-24 font-semibold">Вакансии</h1>
        </div>
        <Link to="/employer/vacancies/new" className={`${linkBtn} bg-brand text-on-brand hover:bg-brand-deep`}>
          Создать вакансию
        </Link>
      </div>
      {q.isPending && (
        <div className="grid gap-3" aria-hidden>
          <Skeleton className="h-24 rounded-xl" />
          <Skeleton className="h-24 rounded-xl" />
        </div>
      )}
      {q.isError && <ErrorState title="Не удалось загрузить вакансии" onRetry={() => void q.refetch()} />}
      {q.isSuccess && list.length === 0 && (
        <EmptyState
          title="Вакансий пока нет"
          description="Опишите роль, грейд, навыки и вилку: система подберёт подходящие профили."
          action={
            <Link to="/employer/vacancies/new" className={`${linkBtn} bg-brand text-on-brand hover:bg-brand-deep`}>
              Создать вакансию
            </Link>
          }
        />
      )}
      {list.length > 0 && (
        <ul aria-label="Вакансии" className="overflow-hidden rounded-xl border border-hairline bg-card shadow-xs">
          {list.map((v) => (
            <li key={v.id} className="grid gap-3 border-b border-hairline p-4 last:border-b-0 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
              <div className="grid min-w-0 gap-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Link to={`/employer/vacancies/${v.id}`} className="font-mono text-16 font-semibold hover:underline">
                    {v.title}
                  </Link>
                  <Badge variant={v.status === "published" ? "success" : "muted"}>{VACANCY_STATUS_LABEL[v.status] ?? v.status}</Badge>
                </div>
                <p className="text-13 text-muted">
                  {roleLabel(v.role)} · {GRADE_LABEL[v.grade_min]}–{GRADE_LABEL[v.grade_max]} · {v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")} ·{" "}
                  {EMPLOYMENT_LABEL[v.employment_type] ?? v.employment_type}
                  {v.city ? ` · ${v.city}` : ""}
                </p>
                <p className="font-mono text-14 font-semibold">{formatRubRange(v.salary_from, v.salary_to)}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link to={`/employer/vacancies/${v.id}`} className={`${linkBtn} border border-hairline text-ink hover:bg-tint-50`}>
                  Редактировать
                </Link>
                <Link to={`/employer/vacancies/${v.id}/shortlist`} className={`${linkBtn} bg-brand text-on-brand hover:bg-brand-deep`}>
                  Подборка
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
