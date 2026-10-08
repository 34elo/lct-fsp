import { useState } from "react";
import { Link } from "react-router-dom";

import { Button, EmptyState, ErrorState, Select, SkeletonCard, SkillChip, formatRubRange } from "@fsp/ui";

import { useListPublicVacanciesVacanciesPublicGet } from "@/api/endpoints/vacancies/vacancies";
import { RoleSlug, type PublicVacancyOut } from "@/api/model";
import { fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { JOBS_TEXT as T } from "./text";

const PAGE = 20;

export function gradeSpan(v: Pick<PublicVacancyOut, "grade_min" | "grade_max">): string {
  const a = GRADE_LABEL[v.grade_min] ?? v.grade_min;
  const b = GRADE_LABEL[v.grade_max] ?? v.grade_max;
  return a === b ? a : `${a}–${b}`;
}

export function JobCard({ v }: { v: PublicVacancyOut }) {
  const place = [v.company.name, v.city, v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ").toLowerCase()].filter(Boolean).join(" · ");
  return (
    <li className="flex flex-col gap-3 rounded-2xl border border-hairline bg-card p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="break-words font-mono text-18 font-semibold">{v.title}</h2>
          <p className="text-13 text-muted">
            {place}
            {v.company.verified && <span className="ml-2 text-success">{T.verified}</span>}
          </p>
        </div>
      </div>
      <p className="font-mono text-22 font-semibold text-brand-deep dark:text-brand-mid">{formatRubRange(v.salary_from, v.salary_to)}</p>
      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-md bg-brand px-2 py-0.5 font-mono text-12 font-semibold text-on-brand">
          {roleLabel(v.role)} · {gradeSpan(v)}
        </span>
        {v.skills.slice(0, 4).map((s) => (
          <SkillChip key={s.slug} name={s.slug} variant="claimed" />
        ))}
      </div>
      <Link to={`/jobs/${v.id}`} className="inline-flex h-11 items-center self-start rounded-lg border border-brand px-4 text-14 font-semibold text-brand-fg hover:bg-tint-50">
        {T.open}
      </Link>
    </li>
  );
}

/** Публичные вакансии (J1): без авторизации, фильтры по профессии, городу и тексту. */
export default function Jobs() {
  const [role, setRole] = useState("");
  const [city, setCity] = useState("");
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const params = { role: (role || undefined) as RoleSlug | undefined, city: city.trim() || undefined, q: q.trim() || undefined, limit };
  const query = useListPublicVacanciesVacanciesPublicGet(params);
  const list = query.data?.status === 200 ? query.data.data : [];
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <p className="font-mono text-12 uppercase tracking-wide text-brand-fg">{T.eyebrow}</p>
        <h1 className="font-mono text-28 font-semibold">{T.title}</h1>
        <p className="max-w-2xl text-14 text-muted">{T.lead}</p>
      </header>
      <div className="grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]">
        <form role="search" onSubmit={(e) => e.preventDefault()} className="grid content-start gap-3">
          <div className="flex flex-col gap-1 text-13 font-semibold">
            <span>{T.role}</span>
            <Select
              aria-label={T.role}
              value={role}
              onChange={(v) => {
                setRole(v ?? "");
                setLimit(PAGE);
              }}
              options={[{ value: "", label: T.anyRole }, ...Object.values(RoleSlug).map((r) => ({ value: r, label: roleLabel(r) }))]}
              className="font-normal"
            />
          </div>
          <label className="flex flex-col gap-1 text-13 font-semibold">
            {T.city}
            <input value={city} onChange={(e) => { setCity(e.target.value); setLimit(PAGE); }} className={fieldClass} />
          </label>
          <label className="flex flex-col gap-1 text-13 font-semibold">
            {T.query}
            <input value={q} onChange={(e) => { setQ(e.target.value); setLimit(PAGE); }} className={fieldClass} />
          </label>
        </form>
        <section aria-label={T.title} className="flex flex-col gap-3">
          {query.isPending && (
            <div className="grid gap-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {query.isError && <ErrorState title={T.loadError} onRetry={() => void query.refetch()} />}
          {query.isSuccess && list.length === 0 && <EmptyState title={T.empty} description={T.emptyHint} />}
          {list.length > 0 && <ul className="grid gap-3">{list.map((v) => <JobCard key={v.id} v={v} />)}</ul>}
          {list.length >= limit && limit < 100 && (
            <Button variant="outline" className="self-center" onClick={() => setLimit(Math.min(100, limit + PAGE))}>{T.more}</Button>
          )}
        </section>
      </div>
    </div>
  );
}
