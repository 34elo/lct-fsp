import { Link } from "react-router-dom";

import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import { ErrorNote } from "@/features/auth/ui";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { EMPLOYMENT_LABEL, FORMAT_LABEL, rub, VACANCY_STATUS_LABEL } from "./text";

/** Свои вакансии (экран E3, список): отсюда идём в подборку. */
export default function Vacancies() {
  const q = useListVacanciesVacanciesGet();
  const list = q.data?.status === 200 ? q.data.data : [];
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 md:p-6">
      <h1 className="font-mono text-2xl font-semibold">Вакансии</h1>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Не удалось загрузить вакансии.</ErrorNote>}
      {q.isSuccess && list.length === 0 && (
        <p className="rounded-xl border border-hairline bg-card p-5 text-sm">Вакансий пока нет. Создание вакансии появится в следующей версии.</p>
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {list.map((v) => (
          <li key={v.id} className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4 shadow-card">
            <div className="flex items-start justify-between gap-3">
              <h2 className="font-mono text-[17px] font-semibold">{v.title}</h2>
              <span className="whitespace-nowrap rounded-md bg-tint-50 px-2 py-1 text-xs font-semibold text-brand-deep dark:text-brand-mid">
                {VACANCY_STATUS_LABEL[v.status] ?? v.status}
              </span>
            </div>
            <p className="text-[13px] text-muted">
              {roleLabel(v.role)} · {GRADE_LABEL[v.grade_min]}–{GRADE_LABEL[v.grade_max]} ·{" "}
              {v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")} · {EMPLOYMENT_LABEL[v.employment_type] ?? v.employment_type}
            </p>
            <p className="font-mono text-sm font-semibold">
              {rub(v.salary_from)} – {rub(v.salary_to)}
              {v.city ? <span className="font-sans font-normal text-muted"> · {v.city}</span> : null}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {v.skills.slice(0, 6).map((s) => (
                <span key={s.slug} className="rounded-md border border-tint-200 bg-tint-50 px-2 py-1 font-mono text-xs text-brand-deep dark:text-brand-mid">
                  {s.slug}
                </span>
              ))}
            </div>
            <Link
              to={`/employer/vacancies/${v.id}/shortlist`}
              className="inline-flex h-9 items-center self-start rounded-lg bg-brand px-3 text-sm font-semibold text-on-brand hover:bg-brand-deep"
            >
              Подборка кандидатов
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
