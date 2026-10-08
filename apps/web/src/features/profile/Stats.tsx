import { PAGE } from "@/shared/lib/page";
import { Gi, Gloss } from "@/shared/Gloss";
import { ActivityHeatmap, buttonVariants, Chips, cn, ConstellationAvatar, EmptyState, ErrorState, formatRub, formatRubRangeShort, GradeTag, H1, H2, Lbl, MetricTile, Num, Panel, PanelCap, ScatterPlot, Skeleton, SkillTag, StatusTag } from "@fsp/ui";
import { useMemo, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { useHistoryAssessmentHistoryGet } from "@/api/endpoints/assessment/assessment";
import { useGetProfileCandidatesMeProfileGet, useMyViewsCandidatesMeViewsGet } from "@/api/endpoints/candidates/candidates";
import { useMyInterestsCandidatesMeInterestsGet } from "@/api/endpoints/offers/offers";
import { useMyNavigatorCandidatesMeNavigatorGet, useMyStandingCandidatesMeStandingGet } from "@/api/endpoints/search/search";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { AttemptOut, CandidateProfile, CandidateStanding, InterestsSummary } from "@/api/model";
import { GRADE } from "@/features/assessment/text";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import { FspCard } from "./Home";
import { dayMonth, nextStep, sortSkills } from "./home-model";
import { finishedAttempts, parseViews, scatter, viewsSeries, type ViewsStats } from "./stats-model";
import { HOME, STATS, roleLabel } from "./text";

const PENDING = new Set(["interest", "interest_opened"]);
const gradeLabel = (g: string) => GRADE[g] ?? g;

function Tiles({ standing, interests, views }: { standing: CandidateStanding; interests?: InterestsSummary; views?: ViewsStats }) {
  const s = standing.strength;
  const range =
    interests?.salary_from_min != null && interests.salary_to_max != null ? formatRubRangeShort(interests.salary_from_min, interests.salary_to_max) : undefined;
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 lg:gap-4" data-testid="stats-tiles">
      <MetricTile label={HOME.strength} info={<Gi k="strength" />} value={s ? Math.round(s.value * 100) : HOME.none} />
      <MetricTile label={HOME.place} info={<Gi k="category" />} value={s ? HOME.top(s.top_percent) : HOME.none} progress={s ? 100 - s.top_percent : undefined} />
      <MetricTile label={HOME.interestsTile} info={<Gi k="interest" />} value={interests ? interests.companies : HOME.none} hint={range} />
      <MetricTile label={STATS.views} value={views ? views.companies : HOME.none} hint={views ? STATS.viewsHint : undefined} />
    </div>
  );
}

function PeersCard({ standing, category }: { standing: CandidateStanding; category: string }) {
  const { points, you } = scatter(standing.peers ?? [], standing.strength?.value);
  return (
    <Panel data-testid="stats-peers" aria-label={STATS.peers}>
      <PanelCap title={<Gloss k="strength"><H2>{STATS.peers}</H2></Gloss>} aside={<Lbl>{STATS.peersSize(standing.category_size ?? 0)}</Lbl>} />
      <ScatterPlot points={points} you={you} youLabel={STATS.you} yLabel={STATS.yLabel} label={STATS.peersLabel(category)} />
    </Panel>
  );
}

function ViewsCard({ views }: { views: ViewsStats }) {
  const series = useMemo(() => viewsSeries(views.byDay, new Date()), [views.byDay]);
  return (
    <Panel className="flex flex-col gap-2.5" data-testid="stats-views" aria-label={STATS.heatmap}>
      <PanelCap title={STATS.heatmap} className="mb-0" />
      <ActivityHeatmap values={series} cell={14} label={STATS.heatmapLabel(views.total)} />
      <Num className="text-12">{STATS.heatmapCaption(views.companies)}</Num>
    </Panel>
  );
}

/** Превью анонимной карточки: что видит работодатель до принятия приглашения. */
function SeenAs({ p, standing, prof }: { p: CandidateProfile; standing: CandidateStanding; prof: string }) {
  const skills = sortSkills(p.skills ?? []).slice(0, 3);
  const top = skills.find((s) => !s.claimed_only)?.skill.name;
  return (
    <Panel className="flex flex-col gap-2.5" data-testid="stats-seen-as" aria-label={STATS.seenAs}>
      <PanelCap title={STATS.seenAs} className="mb-0" />
      <div className="flex items-center gap-3">
        <span className="grid size-11 flex-none place-items-center overflow-hidden rounded-lg border border-tint-200 bg-tint-50">
          <ConstellationAvatar seed={p.pseudonym} size={36} />
        </span>
        <div className="flex min-w-0 flex-col items-start gap-1">
          <span className="break-words font-mono text-14 font-semibold">{displayPseudonym(p.pseudonym, prof)}</span>
          {p.fsp?.verified && <StatusTag>{STATS.fspConfirmed}</StatusTag>}
        </div>
      </div>
      {standing.grade && (
        <Chips>
          <GradeTag>{[gradeLabel(standing.grade), prof, top].filter(Boolean).join(" · ")}</GradeTag>
        </Chips>
      )}
      {skills.length > 0 && (
        <Chips>
          {skills.map((s) => (
            <SkillTag key={s.skill.slug} name={s.skill.name} level={s.claimed_only ? 0 : Math.round(s.level)} state={s.claimed_only ? "claimed" : "confirmed"} />
          ))}
        </Chips>
      )}
      {p.preferences.salary_min != null && (
        <p className="text-13 text-muted">
          {HOME.expectations} <Num className="text-ink">{HOME.salaryFrom(formatRub(p.preferences.salary_min))}</Num>
        </p>
      )}
    </Panel>
  );
}

function HistoryCard({ attempts, profTitle }: { attempts: AttemptOut[]; profTitle: (s: string) => string }) {
  const rows = finishedAttempts(attempts);
  if (!rows.length) return null;
  return (
    <Panel data-testid="stats-history" aria-label={STATS.history}>
      <PanelCap title={STATS.history} aside={<Num className="text-12 text-muted">{rows.length}</Num>} />
      <ul className="flex flex-col gap-3">
        {rows.map((a) => {
          const passed = a.status === "passed";
          const grade = (passed && a.result?.grade) || a.declared_grade;
          return (
            <li key={a.id} className="flex flex-wrap items-center gap-2" data-testid="stats-attempt">
              <GradeTag claimed={!passed}>{[gradeLabel(grade), profTitle(a.profession)].join(" · ")}</GradeTag>
              <StatusTag state={passed ? "confirmed" : "claimed"}>{passed ? STATS.passed : STATS.failed}</StatusTag>
              <Num className="w-full text-12 text-muted">
                {[a.mode ? (STATS.mode[a.mode] ?? a.mode) : null, dayMonth(a.finished_at)].filter(Boolean).join(" · ")}
              </Num>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function StatsSkeleton() {
  return (
    <div className="flex flex-col gap-3" data-testid="stats-loading">
      <p role="status" className="sr-only">
        {STATS.loading}
      </p>
      <Skeleton className="h-7 w-[220px]" />
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4 lg:gap-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    </div>
  );
}

/**
 * Статистика кандидата `/me/stats` (E38-2, макеты v2_me-stats__*, бриф §6.1): плитки «Сила», «Место», «Интересы», «Смотрели»;
 * «Где ты среди своих» и просмотры профиля слева, «Как тебя видят», ФСП и история тестов справа.
 * Без действующего грейда — пустое состояние с одной кнопкой «Пройти тест».
 */
export default function Stats() {
  const pq = useGetProfileCandidatesMeProfileGet();
  const sq = useMyStandingCandidatesMeStandingGet({ query: { refetchOnMount: "always", retry: false } });
  const hq = useHistoryAssessmentHistoryGet({ query: { retry: false } });
  const vq = useMyViewsCandidatesMeViewsGet({ query: { retry: false } });
  const iq = useMyInterestsCandidatesMeInterestsGet({ query: { retry: false } });
  const nq = useMyNavigatorCandidatesMeNavigatorGet({ query: { retry: false } });
  const tq = useGetProfessionsTaxonomyProfessionsGet();

  const page = (body: ReactNode, action?: ReactNode, title = true) => (
    <div className={PAGE.normal} data-testid="stats-page">
      {title && (
        <div className="flex flex-col gap-2.5 md:flex-row md:items-center md:justify-between">
          <H1 className="text-[22px] leading-[1.2] md:text-[26px]">{STATS.title}</H1>
          {action}
        </div>
      )}
      {body}
    </div>
  );

  if (pq.isPending || sq.isPending) return page(<StatsSkeleton />, undefined, false);
  const failed = pq.isError ? pq : sq.isError ? sq : null;
  if (failed || pq.data?.status !== 200 || sq.data?.status !== 200) {
    const status = failed?.error?.status;
    return page(
      <div className="w-full max-w-2xl" data-testid="stats-error">
        <ErrorState
          title={STATS.loadError}
          code={status ? STATS.errorCode(status) : undefined}
          onRetry={() => {
            void pq.refetch();
            void sq.refetch();
          }}
        />
      </div>,
    );
  }

  const p = pq.data.data;
  const standing = sq.data.data;
  if (!standing.grade)
    return page(
      <EmptyState
        className="min-h-[200px]"
        title={STATS.empty}
        action={
          <Link to="/me/assessment" className={buttonVariants({ size: "lg" })} data-testid="stats-empty-action">
            {STATS.emptyAction}
          </Link>
        }
      />,
    );

  const rawHistory = hq.data?.status === 200 ? hq.data.data : undefined;
  const attempts = rawHistory && Array.isArray(rawHistory.attempts) ? rawHistory.attempts : [];
  const views = vq.data?.status === 200 ? parseViews(vq.data.data) : undefined;
  const interests = iq.data?.status === 200 ? iq.data.data : undefined;
  const navigator = nq.data?.status === 200 ? nq.data.data : undefined;
  const professions = tq.data?.status === 200 ? tq.data.data.professions : [];
  const profTitle = (slug: string) => professions.find((x) => x.slug === slug)?.title ?? roleLabel(slug);
  const prof = standing.profession ? profTitle(standing.profession) : "";

  const t = navigator?.test;
  const ns = nextStep({
    tested: true,
    fspLinked: Boolean(p.fsp?.verified),
    pendingInterests: (interests?.items ?? []).filter((o) => PENDING.has(o.status)).length,
    nextTest: t ? { grade: gradeLabel(t.grade), path: t.path } : null,
  });
  const action = ns.current ?? { key: "done", label: HOME.allDone, to: "/me/offers" };

  return page(
    <div className="flex flex-col gap-4" data-testid="stats-main">
      <Tiles standing={standing} interests={interests} views={views} />
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-start">
        <div className="flex flex-col gap-4 lg:col-span-7">
          <PeersCard standing={standing} category={[prof, gradeLabel(standing.grade)].filter(Boolean).join(" ")} />
          {views && <ViewsCard views={views} />}
        </div>
        <div className="flex flex-col gap-4 lg:col-span-5">
          <SeenAs p={p} standing={standing} prof={prof} />
          <FspCard p={p} className="" testId="stats-fsp" />
          <HistoryCard attempts={attempts} profTitle={profTitle} />
        </div>
      </div>
    </div>,
    <Link to={action.to} className={cn(buttonVariants({ size: "lg" }), "w-full md:w-auto")} data-testid="stats-action">
      {action.label}
    </Link>,
  );
}
