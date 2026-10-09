import { useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
  Button,
  EmptyState,
  ErrorState,
  ProfessionInput,
  SalaryRangeInput,
  Select,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
  SkeletonCard,
  SkillChip,
  SkillInput,
  formatRubRange,
  type SkillValue,
} from "@fsp/ui";

import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import { useListPublicVacanciesVacanciesPublicGet } from "@/api/endpoints/vacancies/vacancies";
import type { ListPublicVacanciesVacanciesPublicGetParams, PublicVacancyOut } from "@/api/model";
import { fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { suggestProfessions, useSkillSource } from "@/shared/lib/skills";
import { JOBS_TEXT as T } from "./text";

const PAGE = 20;

export function gradeSpan(v: Pick<PublicVacancyOut, "grade_min" | "grade_max">): string {
  const a = GRADE_LABEL[v.grade_min] ?? v.grade_min;
  const b = GRADE_LABEL[v.grade_max] ?? v.grade_max;
  return a === b ? a : `${a}–${b}`;
}

export function JobCard({ v, search = "" }: { v: PublicVacancyOut; search?: string }) {
  const place = [v.company.name, v.city, v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ").toLowerCase()].filter(Boolean).join(" · ");
  return (
    <li className="flex flex-col gap-3 rounded-2xl border border-hairline bg-card p-4 md:p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="break-words font-mono text-18 font-semibold">{v.title}</h2>
          <p className="text-13 text-muted">
            {place}
            {v.company.verified && <span className="ml-2 text-success">{T.verified}</span>}
            {v.company.demo && <span className="ml-2 text-muted" data-testid="company-demo">{T.demo}</span>}
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
      <Link
        to={`/jobs/${v.id}`}
        state={{ search }}
        className="inline-flex h-11 items-center self-start rounded-lg border border-brand px-4 text-14 font-semibold text-brand-fg hover:bg-tint-50"
      >
        {T.open}
      </Link>
    </li>
  );
}

interface Filters {
  q: string;
  role: string;
  grade: string;
  skills: string[];
  smin: number | null;
  smax: number | null;
  format: string;
  city: string;
}

const num = (s: string | null): number | null => {
  const n = s ? Number(s) : NaN;
  return Number.isFinite(n) && n > 0 ? n : null;
};

/** Фильтры живут в адресной строке: ссылку можно сохранить, а «Назад к списку» возвращает на тот же поиск. */
function readFilters(sp: URLSearchParams): Filters {
  return {
    q: sp.get("q") ?? "",
    role: sp.get("role") ?? "",
    grade: sp.get("grade") ?? "",
    skills: (sp.get("skills") ?? "").split(",").filter(Boolean),
    smin: num(sp.get("smin")),
    smax: num(sp.get("smax")),
    format: sp.get("format") ?? "",
    city: sp.get("city") ?? "",
  };
}

function writeFilters(f: Filters): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q) sp.set("q", f.q);
  if (f.role) sp.set("role", f.role);
  if (f.grade) sp.set("grade", f.grade);
  if (f.skills.length) sp.set("skills", f.skills.join(","));
  if (f.smin) sp.set("smin", String(f.smin));
  if (f.smax) sp.set("smax", String(f.smax));
  if (f.format) sp.set("format", f.format);
  if (f.city) sp.set("city", f.city);
  return sp;
}

const GRADES = ["intern", "junior", "junior_plus", "middle", "middle_plus", "senior", "lead"];

function FilterFields({ f, set }: { f: Filters; set: (patch: Partial<Filters>) => void }) {
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const professions = pq.data?.status === 200 ? pq.data.data.professions : [];
  const { suggest, nameOf } = useSkillSource();
  const skillValue: SkillValue[] = f.skills.map((s) => ({ value: s, label: nameOf(s) }));
  return (
    <div className="grid content-start gap-3">
      <div className="flex flex-col gap-1 text-13 font-semibold">
        <span>{T.role}</span>
        <ProfessionInput value={f.role || null} onChange={(v) => set({ role: v ?? "" })} professions={professions} suggest={suggestProfessions} placeholder={T.anyRole} clearable aria-label={T.role} />
      </div>
      <div className="flex flex-col gap-1 text-13 font-semibold">
        <span>{T.grade}</span>
        <Select
          aria-label={T.grade}
          value={f.grade}
          onChange={(v) => set({ grade: v ?? "" })}
          options={[{ value: "", label: T.anyGrade }, ...GRADES.map((g) => ({ value: g, label: GRADE_LABEL[g] ?? g }))]}
          className="font-normal"
        />
      </div>
      <div className="flex flex-col gap-1 text-13 font-semibold">
        <span>{T.skillsFilter}</span>
        <SkillInput
          value={skillValue}
          onChange={(v) => set({ skills: v.filter((x) => !x.isNew).map((x) => x.value) })}
          suggest={suggest}
          allowNew={false}
          max={10}
          placeholder={T.skillsPlaceholder}
          aria-label={T.skillsFilter}
        />
      </div>
      <div className="flex flex-col gap-1 text-13 font-semibold">
        <span>{T.salary}</span>
        <SalaryRangeInput value={{ from: f.smin, to: f.smax }} onChange={(v) => set({ smin: v.from, smax: v.to })} slider={false} />
      </div>
      <div className="flex flex-col gap-1 text-13 font-semibold">
        <span>{T.format}</span>
        <Select
          aria-label={T.format}
          value={f.format}
          onChange={(v) => set({ format: v ?? "" })}
          options={[{ value: "", label: T.anyFormat }, ...Object.entries(FORMAT_LABEL).map(([value, label]) => ({ value, label }))]}
          className="font-normal"
        />
      </div>
      <label className="flex flex-col gap-1 text-13 font-semibold">
        {T.city}
        <input value={f.city} onChange={(e) => set({ city: e.target.value })} className={fieldClass} />
      </label>
    </div>
  );
}

type Params = ListPublicVacanciesVacanciesPublicGetParams;

/** Публичные вакансии (J1): поиск сверху, фильтры сбоку (на телефоне — шторка), состояние в URL. */
export default function Jobs() {
  const [sp, setSp] = useSearchParams();
  const loc = useLocation();
  const f = useMemo(() => readFilters(sp), [sp]);
  const [limit, setLimit] = useState(PAGE);
  const [sheet, setSheet] = useState(false);
  const set = (patch: Partial<Filters>) => {
    setSp(writeFilters({ ...f, ...patch }), { replace: true });
    setLimit(PAGE);
  };
  const reset = () => setSp(writeFilters({ ...f, role: "", grade: "", skills: [], smin: null, smax: null, format: "", city: "" }), { replace: true });
  const active = [f.role, f.grade, f.skills.length, f.smin, f.smax, f.format, f.city].filter(Boolean).length;
  const params: Params = {
    q: f.q.trim() || undefined,
    role: f.role || undefined,
    grade: (f.grade || undefined) as Params["grade"],
    skills: f.skills.length ? f.skills : undefined,
    salary_min: f.smin ?? undefined,
    salary_max: f.smax ?? undefined,
    format: (f.format || undefined) as Params["format"],
    city: f.city.trim() || undefined,
    limit,
  };
  const query = useListPublicVacanciesVacanciesPublicGet(params);
  const list = query.data?.status === 200 ? query.data.data : [];
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <p className="font-mono text-12 uppercase tracking-wide text-brand-fg">{T.eyebrow}</p>
        <h1 className="font-mono text-28 font-semibold">{T.title}</h1>
        <p className="max-w-2xl text-14 text-muted">{T.lead}</p>
      </header>
      <form role="search" onSubmit={(e) => e.preventDefault()} className="flex gap-2">
        <input
          type="search"
          value={f.q}
          onChange={(e) => set({ q: e.target.value })}
          placeholder={T.searchPlaceholder}
          aria-label={T.query}
          className={`${fieldClass} min-w-0 flex-1`}
        />
        <Sheet open={sheet} onOpenChange={setSheet}>
          <SheetTrigger asChild>
            <Button type="button" variant="outline" className="lg:hidden">
              {T.filters}
              {active > 0 && <span className="ml-1 font-mono text-12">{active}</span>}
            </Button>
          </SheetTrigger>
          <SheetContent side="bottom" className="flex flex-col gap-4 lg:hidden">
            <SheetTitle className="font-mono text-18 font-semibold">{T.filtersTitle}</SheetTitle>
            <FilterFields f={f} set={set} />
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={reset}>
                {T.reset}
              </Button>
              <Button type="button" className="flex-1" onClick={() => setSheet(false)}>
                {T.showResults}
              </Button>
            </div>
          </SheetContent>
        </Sheet>
      </form>
      <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside aria-label={T.filtersTitle} className="hidden content-start gap-3 lg:grid">
          <FilterFields f={f} set={set} />
          {active > 0 && (
            <Button type="button" variant="outline" onClick={reset}>
              {T.reset}
            </Button>
          )}
        </aside>
        <section aria-label={T.title} className="flex flex-col gap-3">
          {query.isPending && (
            <div className="grid gap-3">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          )}
          {query.isError && <ErrorState title={T.loadError} onRetry={() => void query.refetch()} />}
          {query.isSuccess && list.length === 0 && <EmptyState title={T.empty} description={T.emptyHint} />}
          {list.length > 0 && (
            <ul className="grid gap-3">
              {list.map((v) => (
                <JobCard key={v.id} v={v} search={loc.search} />
              ))}
            </ul>
          )}
          {list.length >= limit && limit < 100 && (
            <Button variant="outline" className="self-center" onClick={() => setLimit(Math.min(100, limit + PAGE))}>
              {T.more}
            </Button>
          )}
        </section>
      </div>
    </div>
  );
}
