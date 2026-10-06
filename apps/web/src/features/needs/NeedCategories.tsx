import { Link, useLocation, useParams } from "react-router-dom";

import { buttonVariants, cn, EmptyState, ErrorState, formatRub, GradeBadge, SectionLabel, Skeleton } from "@fsp/ui";

import { useNeedCategoriesNeedsNeedIdCategoriesGet } from "@/api/endpoints/needs/needs";
import type { NeedCategory, NeedOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { FORMAT_LABEL } from "@/features/employer/text";
import { GRADE_LABEL, ROLE_LABEL } from "@/features/profile/text";
import { fixed2, gradeTitle } from "./need-model";
import { NEED_TEXT as T } from "./text";

/** Что поняли из текста: роли, навыки (по весу), грейды, формат, бюджет. */
export function needChips(need: NeedOut): string[] {
  const f = need.filters;
  const out: string[] = [];
  for (const r of f.roles ?? []) out.push(ROLE_LABEL[r] ?? r);
  for (const [slug] of Object.entries(need.skills).sort((a, b) => b[1] - a[1])) out.push(slug);
  for (const g of need.grades) out.push(GRADE_LABEL[g] ?? g);
  for (const fm of f.formats ?? []) out.push(FORMAT_LABEL[fm] ?? fm);
  if (f.salary_max) out.push(`до ${formatRub(f.salary_max)}`);
  return out;
}

function CategoryCard({ c, needId, best }: { c: NeedCategory; needId: string; best: boolean }) {
  const few = c.candidates > 0 && c.candidates < 5;
  const cell = (label: string, value: string) => (
    <div className="grid gap-0.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-mono text-14 font-semibold">{value}</dd>
    </div>
  );
  return (
    <li>
      <article aria-label={`${c.title}, ${gradeTitle(c.grade)}`} className="grid h-full content-start gap-4 rounded-xl border border-hairline bg-card p-4 shadow-xs">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-mono text-16 font-semibold">{c.title}</h3>
          <GradeBadge grade={gradeTitle(c.grade)} />
          {best && <span className="rounded-md bg-tint-50 px-2 py-0.5 text-12 font-semibold text-brand-fg">{T.best}</span>}
        </div>
        {few && <p className="text-12 font-semibold text-warning-fg">⚠ {T.few}</p>}
        <dl className="grid grid-cols-2 gap-3">
          {cell(T.affinity, fixed2(c.affinity))}
          {cell(T.candidates, String(c.candidates))}
          {cell(T.median, c.median_salary ? formatRub(c.median_salary) : T.noData)}
          {cell(T.fsp, c.fsp_share === null || c.fsp_share === undefined ? T.noData : `${Math.round(c.fsp_share * 100)}%`)}
        </dl>
        <Link
          to={`/employer/categories/${c.profession}/${c.grade}?need_id=${needId}`}
          className={cn(buttonVariants({ variant: best ? "default" : "outline" }), "mt-auto")}
        >
          {T.open(c.candidates)}
        </Link>
      </article>
    </li>
  );
}

/** Рекомендованные категории по потребности (макет N1). */
export default function NeedCategories() {
  const { id = "" } = useParams();
  const need = (useLocation().state as { need?: NeedOut } | null)?.need;
  const q = useNeedCategoriesNeedsNeedIdCategoriesGet(id);
  const cats = q.data?.status === 200 ? q.data.data.categories : [];
  const chips = need ? needChips(need) : [];

  return (
    <div className="grid gap-6 px-4 py-6 md:px-6 lg:px-10 lg:py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="grid gap-2">
          <SectionLabel>{T.kicker}</SectionLabel>
          <h1 className="font-mono text-24 font-semibold">{T.recommended}</h1>
          <p className="text-13 text-muted">{T.shown}</p>
        </div>
        <Link to="/employer/needs/new" className={buttonVariants({ variant: "outline" })}>
          {T.newNeed}
        </Link>
      </header>

      {chips.length > 0 && (
        <section aria-label={T.understood} className="flex flex-wrap items-center gap-2">
          <span className="lbl mr-1 text-muted">{T.understood}</span>
          <ul className="flex flex-wrap gap-2">
            {chips.map((c) => (
              <li key={c} className="inline-flex h-[30px] items-center rounded-md border border-tint-200 bg-tint-50 px-3 font-mono text-[12.5px] font-medium text-brand-deep dark:text-brand-mid">
                {c}
              </li>
            ))}
          </ul>
        </section>
      )}

      {q.isPending && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-hidden>
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-52 rounded-xl" />
        </div>
      )}
      {q.isError &&
        (q.error instanceof ApiError && q.error.status === 404 ? (
          <EmptyState
            title={T.notFound}
            action={
              <Link to="/employer/needs/new" className="font-semibold text-brand-fg hover:underline">
                {T.newNeed}
              </Link>
            }
          />
        ) : (
          <ErrorState title={T.loadFailed} onRetry={() => void q.refetch()} />
        ))}
      {q.isSuccess && cats.length === 0 && <EmptyState title={T.emptyTitle} description={T.emptyHint} />}
      {cats.length > 0 && (
        <ul aria-label={T.list} className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cats.map((c, i) => (
            <CategoryCard key={`${c.profession}:${c.grade}`} c={c} needId={id} best={i === 0} />
          ))}
        </ul>
      )}

      <aside className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-tint-200 bg-tint-50 p-4">
        <div className="grid gap-1">
          <p className="font-mono text-15 font-semibold">{T.vacancyTitle}</p>
          <p className="text-13 text-muted">{T.vacancyHint}</p>
        </div>
        <Link to="/employer/vacancies/new" className={buttonVariants({ variant: "outline" })}>
          {T.vacancyCta}
        </Link>
      </aside>
    </div>
  );
}
