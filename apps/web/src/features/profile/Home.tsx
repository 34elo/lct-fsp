import { PAGE } from "@/shared/lib/page";

import { Gi, Gloss } from "@/shared/Gloss";
import { buttonVariants, Chips, CircuitLine, cn, ConstellationAvatar, type ConstellationNode, dotsText, ErrorState, formatRub, formatRubRangeShort, GradeTag, H1, H2, Lbl, ListRow, MetricTile, Num, Panel, PanelCap, Skeleton, SkillConstellation, SkillTag, StatusTag } from "@fsp/ui";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useHistoryAssessmentHistoryGet, useMyTasksAssessmentTasksGet } from "@/api/endpoints/assessment/assessment";
import { useGetProfileCandidatesMeProfileGet, useMyViewsCandidatesMeViewsGet } from "@/api/endpoints/candidates/candidates";
import { useMyInterestsCandidatesMeInterestsGet, useMyOffersCandidatesMeOffersGet } from "@/api/endpoints/offers/offers";
import { useMyNavigatorCandidatesMeNavigatorGet, useMyStandingCandidatesMeStandingGet } from "@/api/endpoints/search/search";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { CandidateProfile, CandidateStanding, HistoryOut, InterestsSummary, NavigatorOut, OfferForCandidate } from "@/api/model";
import { isFuture, pathStep, type PathStep } from "@/features/assessment/model";
import { GRADE } from "@/features/assessment/text";
import { dateOnly } from "@/features/offers/text";
import { StatusBadge } from "@/features/offers/parts";
import { candStatus } from "@/features/tasks/model";
import { TASKS_TEXT } from "@/features/tasks/text";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import { constellationNodes, dayMonth, formatsText, latestInvites, nextStep, skillSource, sortSkills } from "./home-model";
import { parseViews, type ViewsStats } from "./stats-model";
import { FSP_LEVEL_LABEL, HOME, STATS, roleLabel } from "./text";

const SKILLS_LIMIT = 8;
const PENDING = new Set(["interest", "interest_opened"]);
const gradeLabel = (g: string) => GRADE[g] ?? g;

/** Знак и псевдоним кандидата с городом (шапка карточки профиля). */
function Who({ p, size = 44, big }: { p: CandidateProfile; size?: number; big?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span className="grid flex-none place-items-center overflow-hidden rounded-lg border border-tint-200 bg-tint-50" style={{ width: size, height: size }}>
        <ConstellationAvatar seed={p.pseudonym} size={size - 8} />
      </span>
      <div className="flex min-w-0 flex-col">
        <span className={cn("break-words font-mono font-semibold", big ? "text-20" : "text-16")}>{displayPseudonym(p.pseudonym, p.category?.primary_role)}</span>
        {p.preferences.city && <span className="text-13 text-muted">{p.preferences.city}</span>}
      </div>
    </div>
  );
}

/* ---------- До теста: одна карточка ---------- */

function Before({ p, step, nodes }: { p: CandidateProfile; step: PathStep; nodes: ConstellationNode[] }) {
  const action = (
    <Link to={step.to} className={cn(buttonVariants({ size: "lg" }), "w-full px-8 lg:w-auto")} data-testid="home-start">
      {HOME.beforeAction[step.kind]}
    </Link>
  );
  return (
    <Panel className="flex flex-col overflow-hidden p-0 lg:grid lg:min-h-[680px] lg:grid-cols-12" data-testid="home-before" data-step={step.kind}>
      <div className="contents lg:col-span-5 lg:flex lg:flex-col lg:justify-between lg:gap-8 lg:p-8">
        <div className="order-1 flex flex-col items-start gap-4 p-4 lg:order-none lg:flex-1 lg:gap-6 lg:p-0">
          <Who p={p} />
          <div className="flex flex-1 flex-col items-start gap-6 lg:justify-center">
            <H1 className="text-[22px] leading-[1.25] lg:text-[28px] lg:leading-[1.2]">{HOME.beforeTitle}</H1>
            <span className="hidden lg:block">{action}</span>
          </div>
        </div>
        <div className="order-3 flex flex-col gap-3 p-4 lg:order-none lg:p-0">
          <Chips>
            <SkillTag name={HOME.claimed} state="claimed" />
            <StatusTag>{HOME.express}</StatusTag>
          </Chips>
          <span className="lg:hidden">{action}</span>
        </div>
      </div>
      <div className="order-2 flex min-h-56 flex-1 items-center border-y border-hairline bg-tint-50 lg:order-none lg:col-span-7 lg:border-y-0 lg:border-l">
        {nodes.length > 0 ? (
          <SkillConstellation nodes={nodes} label={HOME.constellationEmpty} />
        ) : (
          <ul className="m-0 flex w-full list-none flex-col gap-3 p-4 lg:p-8" data-testid="home-hints">
            {[
              { ...HOME.hints.data, to: "/me/profile?tab=data" },
              { ...HOME.hints.test, to: step.to },
              { ...HOME.hints.fsp, to: "/me/profile?tab=data" },
            ].map((h) => (
              <li key={h.title}>
                <Link to={h.to} className="flex flex-col gap-1 rounded-xl border border-hairline bg-card p-4 hover:border-brand" data-testid="home-hint">
                  <span className="font-semibold">{h.title}</span>
                  <span className="text-13 text-muted">{h.text}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

/* ---------- После теста ---------- */

function ProfileCard({ p, standing, profTitle, history }: { p: CandidateProfile; standing?: CandidateStanding; profTitle: (s: string) => string; history?: HistoryOut }) {
  const grade = standing?.grade ?? null;
  const claim = p.claimed_vs_confirmed?.[0];
  const lastAttempt = history?.attempts.find((a) => a.status === "passed" || a.status === "failed");
  const profession = standing?.profession ?? claim?.profession ?? lastAttempt?.profession ?? p.category?.primary_role;
  const shownGrade = grade ?? claim?.declared_grade ?? lastAttempt?.declared_grade ?? null;
  const prof = profession ? profTitle(profession) : null;
  const formats = formatsText(p.preferences.formats ?? []);
  return (
    <Panel className="hidden flex-col gap-3 lg:flex" data-testid="home-profile">
      <Who p={p} big />
      {shownGrade && (
        <Chips>
          <GradeTag claimed={!grade} data-testid="home-grade">
            {[gradeLabel(shownGrade), prof].filter(Boolean).join(" · ")}
          </GradeTag>
          <StatusTag state={grade ? "confirmed" : "claimed"} data-testid="home-grade-status">
            {grade ? HOME.confirmed(dayMonth(standing?.confirmed_at), standing?.mode === "express") : HOME.notConfirmed}
          </StatusTag>
        </Chips>
      )}
      {(p.preferences.salary_min != null || formats) && (
        <p className="text-13 text-muted">
          {p.preferences.salary_min != null && (
            <>
              {HOME.expectations} <Num className="text-ink">{HOME.salaryFrom(formatRub(p.preferences.salary_min))}</Num>
              <br />
            </>
          )}
          {formats}
        </p>
      )}
    </Panel>
  );
}

function SkillsCard({ p, className }: { p: CandidateProfile; className?: string }) {
  const skills = p.skills ?? [];
  if (!skills.length) return null;
  return (
    <Panel className={className} data-testid="home-skills" aria-label={HOME.skills}>
      <PanelCap title={<Gloss k="trust"><H2>{HOME.skills}</H2></Gloss>} aside={<Num className="text-12 text-muted">{skills.length}</Num>} />
      {sortSkills(skills)
        .slice(0, SKILLS_LIMIT)
        .map((s) => {
          const src = skillSource(s);
          return (
            <ListRow key={s.skill.slug}>
              <span className="min-w-0 flex-1 truncate font-medium">{s.skill.name}</span>
              <span aria-label={`доверие ${s.claimed_only ? 0 : Math.round(s.level)} из 4`} className="font-mono text-11 font-semibold tracking-[1px] text-brand-fg">
                {dotsText(s.claimed_only ? 0 : s.level)}
              </span>
              <StatusTag state={src.claimed ? "claimed" : "confirmed"}>{src.text}</StatusTag>
            </ListRow>
          );
        })}
      {skills.length > SKILLS_LIMIT && (
        <Link to="/me/profile?tab=skills" className="mt-2 inline-block text-14 font-semibold text-brand-fg hover:underline" data-testid="home-skills-all">
          {HOME.allSkills}
        </Link>
      )}
    </Panel>
  );
}

/** «Достижения ФСП» (три последних); общий для Главной и «Статистики». */
export function FspCard({ p, className = "hidden lg:block", testId = "home-fsp" }: { p: CandidateProfile; className?: string; testId?: string }) {
  const items = p.fsp?.achievements ?? [];
  if (!items.length) return null;
  return (
    <Panel className={className} data-testid={testId} aria-label={HOME.fsp}>
      <PanelCap title={<Gloss k="fspRelevance"><H2>{HOME.fsp}</H2></Gloss>} />
      <ul className="flex flex-col gap-3">
        {items.slice(0, 3).map((a) => (
          <li key={a.fact_id} className="flex items-start gap-3">
            <span aria-hidden className="grid size-7 flex-none place-items-center rounded-full bg-tint-100 font-mono text-12 font-semibold text-chip-fg">
              Ф
            </span>
            <div className="flex min-w-0 flex-col items-start gap-1.5">
              <span className="font-medium">{a.title}</span>
              <StatusTag>{a.place != null ? HOME.fspPlace(a.place) : (FSP_LEVEL_LABEL[a.level] ?? a.level)}</StatusTag>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

function NextStepCard({ p, standing, interests, navigator, history }: { p: CandidateProfile; standing?: CandidateStanding; interests?: InterestsSummary; navigator?: NavigatorOut; history?: HistoryOut }) {
  const t = navigator?.test;
  const ns = nextStep({
    tested: Boolean(standing?.grade),
    fspLinked: Boolean(p.fsp?.verified),
    pendingInterests: (interests?.items ?? []).filter((o) => PENDING.has(o.status)).length,
    nextTest: t ? { grade: gradeLabel(t.grade), path: t.path } : null,
  });
  const cooldown = t && history?.cooldowns.find((c) => c.profession === t.profession && c.grade === t.grade && isFuture(c.next_change_at));
  const action = ns.current ?? { key: "done", label: HOME.allDone, to: "/me/offers" };
  return (
    <Panel className="order-1 flex flex-col gap-3 border-brand md:flex-row md:items-center md:gap-4 lg:order-none" data-testid="home-next" data-step={action.key}>
      <div className="min-w-0 flex-1">
        <Lbl>{HOME.nextStep}</Lbl>
        <CircuitLine steps={ns.steps} orientation="horizontal" className="mt-3" />
        {ns.current?.key === "next" && cooldown && (
          <p className="mt-2 font-mono text-12 text-muted" data-testid="home-cooldown">
            {HOME.cooldown(dayMonth(cooldown.next_change_at))}
          </p>
        )}
      </div>
      <Link to={action.to} className={cn(buttonVariants({ size: "lg" }), "self-start")} data-testid="home-next-action">
        {action.label}
      </Link>
    </Panel>
  );
}

function ConstellationCard({ nodes }: { nodes: ConstellationNode[] }) {
  if (!nodes.length) return null;
  return (
    <Panel className="order-3 lg:order-none" data-testid="home-constellation" aria-label={HOME.constellation}>
      <PanelCap
        title={<Gloss k="graph"><H2>{HOME.constellation}</H2></Gloss>}
        aside={
          <Chips className="hidden md:flex">
            <SkillTag name={HOME.legend.confirmed} />
            <SkillTag name={HOME.legend.claimed} state="claimed" />
            <SkillTag name={HOME.legend.adjacent} state="ghost" />
          </Chips>
        }
      />
      <SkillConstellation nodes={nodes} />
    </Panel>
  );
}

function Interests({ interests, offers }: { interests?: InterestsSummary; offers: OfferForCandidate[] }) {
  const items = latestInvites(interests?.items ?? [], offers);
  if (!items.length) return null;
  const range =
    interests?.salary_from_min != null && interests.salary_to_max != null ? formatRubRangeShort(interests.salary_from_min, interests.salary_to_max) : null;
  const aside = [interests && interests.companies > 0 ? interests.companies : null, range].filter((v) => v != null).join(" · ");
  return (
    <Panel className="order-4 lg:order-none" data-testid="home-interests" aria-label={HOME.interests}>
      <PanelCap title={<Gloss k="invitation"><H2>{HOME.interests}</H2></Gloss>} aside={aside ? <Num className="text-13">{aside}</Num> : undefined} />
      <ul className="m-0 flex list-none flex-col p-0">
        {items.map((o) => (
          <li key={o.id} data-testid="home-invite">
            <Link
              to={o.status === "interest" || o.status === "interest_opened" ? "/me/offers?show=interests" : `/me/offers/${o.id}`}
              className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-3 last:border-b-0 hover:text-brand-fg"
            >
              <span className="min-w-0 flex-1 truncate font-medium">{o.company.name}</span>
              <StatusBadge status={o.status} />
              <Num className="text-13 text-muted">{formatRubRangeShort(o.salary_from, o.salary_to)}</Num>
            </Link>
          </li>
        ))}
      </ul>
      <Link to="/me/offers" className="self-start text-14 font-semibold text-brand-fg hover:underline" data-testid="home-invites-all">
        {HOME.allInvites}
      </Link>
    </Panel>
  );
}

/** Открытые регулярные задания (E39-15: раньше — кнопка в профиле). Нет открытых — блока нет. */
function RegularTasks() {
  const q = useMyTasksAssessmentTasksGet({ query: { retry: false } });
  const open = (q.data?.status === 200 ? q.data.data : []).filter((t) => candStatus(t) === "new");
  if (!open.length) return null;
  return (
    <Panel className="order-4 flex flex-col gap-2 lg:order-none" data-testid="home-tasks" aria-label={HOME.tasks}>
      <PanelCap title={<H2>{HOME.tasks}</H2>} aside={<Num className="text-13">{open.length}</Num>} />
      <p className="text-13 text-muted">{HOME.tasksHint}</p>
      <ul className="m-0 flex list-none flex-col p-0">
        {open.slice(0, 3).map((t) => (
          <li key={t.id} data-testid="home-task">
            <Link to={`/me/tasks?task=${t.id}`} className="flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-3 last:border-b-0 hover:text-brand-fg">
              <span className="min-w-0 flex-1 truncate font-medium">{t.title}</span>
              {t.answer_until && <Num className="text-13 text-muted">{TASKS_TEXT.until(dateOnly(t.answer_until))}</Num>}
            </Link>
          </li>
        ))}
      </ul>
      <Link to="/me/tasks" className="self-start text-14 font-semibold text-brand-fg hover:underline" data-testid="home-tasks-all">
        {HOME.tasksAll}
      </Link>
    </Panel>
  );
}

function Tiles({ standing, interests, profTitle }: { standing?: CandidateStanding; interests?: InterestsSummary; profTitle: (s: string) => string }) {
  const s = standing?.strength;
  const range =
    interests?.salary_from_min != null && interests.salary_to_max != null ? formatRubRangeShort(interests.salary_from_min, interests.salary_to_max) : undefined;
  return (
    <div className="order-2 grid grid-cols-2 gap-2 lg:order-none lg:grid-cols-1 lg:gap-4" data-testid="home-tiles">
      <MetricTile
        label={HOME.place}
        info={<Gi k="strength" />}
        value={s ? HOME.topCap(s.top_percent) : HOME.none}
        hint={s && standing?.profession && standing.grade ? `${profTitle(standing.profession)} ${GRADE[standing.grade] ?? standing.grade}` : undefined}
        progress={s ? 100 - s.top_percent : undefined}
      />
      <MetricTile label={HOME.interestsTile} info={<Gi k="interest" />} value={interests ? interests.companies : HOME.none} hint={range} />
    </div>
  );
}

/** Ссылка на «Статистику» (`/me/stats`, E38-2) под плитками. */
function StatsLink({ views }: { views?: ViewsStats }) {
  return (
    <Link
      to="/me/stats"
      className="order-6 flex items-center justify-between gap-3 rounded-xl border border-hairline bg-card p-4 font-semibold hover:border-brand lg:order-none"
      data-testid="home-stats"
    >
      <span>{STATS.link}</span>
      {views && <Num className="text-12 text-muted">{STATS.linkViews(views.companies)}</Num>}
    </Link>
  );
}

function After(props: {
  p: CandidateProfile;
  standing?: CandidateStanding;
  interests?: InterestsSummary;
  navigator?: NavigatorOut;
  offers: OfferForCandidate[];
  history?: HistoryOut;
  views?: ViewsStats;
  profTitle: (s: string) => string;
}) {
  const { p, navigator } = props;
  const nodes = constellationNodes(p.skills ?? [], { adjacent: (navigator?.skill_gaps ?? []).map((g) => g.name) });
  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-start" data-testid="home-after">
      <div className="contents lg:col-span-3 lg:flex lg:flex-col lg:gap-4">
        <ProfileCard {...props} />
        <SkillsCard p={p} className="order-5 lg:order-none" />
        <FspCard p={p} />
      </div>
      <div className="contents lg:col-span-6 lg:flex lg:flex-col lg:gap-4">
        <NextStepCard {...props} />
        <ConstellationCard nodes={nodes} />
        <Interests interests={props.interests} offers={props.offers} />
        <RegularTasks />
      </div>
      <div className="contents lg:col-span-3 lg:flex lg:flex-col lg:gap-4">
        <Tiles standing={props.standing} interests={props.interests} profTitle={props.profTitle} />
        <StatsLink views={props.views} />
      </div>
    </div>
  );
}

function HomeSkeleton() {
  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-start" data-testid="home-loading">
      <p role="status" className="sr-only">
        {HOME.loading}
      </p>
      <div className="hidden flex-col gap-4 lg:col-span-3 lg:flex">
        <Skeleton className="h-48" />
        <Skeleton className="h-40" />
      </div>
      <div className="flex flex-col gap-4 lg:col-span-6">
        <Skeleton className="h-28" />
        <Skeleton className="h-64" />
        <Skeleton className="h-24" />
      </div>
      <div className="grid grid-cols-3 gap-2 lg:col-span-3 lg:grid-cols-1 lg:gap-4">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    </div>
  );
}

/**
 * Главная кандидата `/me` (E38-1, макеты v2_me__before / v2_me__after, бриф §6.1).
 * До теста — одна карточка «Пройди тест» с созвездием заявленных навыков; после — профиль, навыки и ФСП слева,
 * следующий шаг, созвездие и «Вами интересуются» в центре, плитки «Сила», «Место», «Интересы» справа.
 */
export default function Home() {
  const pq = useGetProfileCandidatesMeProfileGet();
  const hq = useHistoryAssessmentHistoryGet({ query: { refetchOnMount: "always", retry: false } });
  const sq = useMyStandingCandidatesMeStandingGet({ query: { refetchOnMount: "always", retry: false } });
  const iq = useMyInterestsCandidatesMeInterestsGet({ query: { retry: false } });
  const oq = useMyOffersCandidatesMeOffersGet(undefined, { query: { retry: false } });
  const nq = useMyNavigatorCandidatesMeNavigatorGet({ query: { retry: false } });
  const tq = useGetProfessionsTaxonomyProfessionsGet();
  const vq = useMyViewsCandidatesMeViewsGet({ query: { retry: false } });

  const page = (body: ReactNode, h1 = true) => (
    <div className={PAGE.normal} data-testid="home-page">
      {h1 && <h1 className="sr-only">{HOME.title}</h1>}
      {body}
    </div>
  );

  if (pq.isPending || hq.isPending) return page(<HomeSkeleton />);
  if (pq.isError || pq.data.status !== 200)
    return page(
      <div className="mx-auto w-full max-w-2xl" data-testid="home-error">
        <ErrorState title={HOME.loadError} description={HOME.loadErrorHint} onRetry={() => void pq.refetch()} />
      </div>,
    );

  const p = pq.data.data;
  const raw = hq.data?.status === 200 ? hq.data.data : undefined;
  // Неполный ответ истории (старый бэкенд, заглушка) — считаем, что путь пройден, экран не роняем (как PathBanner).
  const history = raw && Array.isArray(raw.surveys) && Array.isArray(raw.attempts) ? raw : undefined;
  const standing = sq.data?.status === 200 ? sq.data.data : undefined;
  const interests = iq.data?.status === 200 ? iq.data.data : undefined;
  const offers = oq.data?.status === 200 ? (oq.data.data as unknown as OfferForCandidate[]) : [];
  const navigator = nq.data?.status === 200 ? nq.data.data : undefined;
  const views = vq.data?.status === 200 ? parseViews(vq.data.data) : undefined;
  const professions = tq.data?.status === 200 ? tq.data.data.professions : [];
  const profTitle = (slug: string) => professions.find((x) => x.slug === slug)?.title ?? roleLabel(slug);

  const step = history ? pathStep(history) : null;
  if (step) {
    const survey = [...(history?.surveys ?? [])].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))[0];
    const nodes = constellationNodes(p.skills ?? [], { stack: survey?.stack ?? [], claimedOnly: true });
    return page(<Before p={p} step={step} nodes={nodes} />, false);
  }
  return page(<After p={p} standing={standing} interests={interests} navigator={navigator} offers={offers} history={history} views={views} profTitle={profTitle} />);
}
