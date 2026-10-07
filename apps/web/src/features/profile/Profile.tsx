import {
  Badge,
  Button,
  Chips,
  EmptyState,
  ErrorState,
  FspProtocol,
  GradeTag,
  H1,
  Lbl,
  Num,
  Panel,
  PanelCap,
  Skeleton,
  SkillTag,
  StatusTag,
  Tag,
  TeamSignal as TeamSignalRow,
  buttonVariants,
  cn,
  dotsText,
  formatRub,
  type FspResult,
} from "@fsp/ui";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useGetProfileCandidatesMeProfileGet } from "@/api/endpoints/candidates/candidates";
import { useMyStandingCandidatesMeStandingGet } from "@/api/endpoints/search/search";
import type { CandidateProfile, CandidateStanding, GradeInfo, SkillWithTrust } from "@/api/model";
import { GRADE } from "@/features/assessment/text";
import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";
import GraphView from "@/features/graph/Graph";
import { downloadProfilePdf } from "@/features/profile/pdf";
import { dayMonth, formatsText, sortSkills } from "./home-model";
import {
  CLAIM_STATUS_LABEL,
  DISCIPLINE_LABEL,
  FSP_LEVEL_LABEL,
  GRADE_LABEL,
  HOME,
  PROFILE,
  RANK_LABEL,
  SIGNAL_LABEL,
  SOURCE_TAG,
  STATUS_LABEL,
  STRENGTH_ITEMS,
  T,
  TEAM_ROLE_LABEL,
  periodRu,
  points,
  roleLabel,
} from "./text";
import { useEventStream } from "@/shared/lib/useEventStream";

const PAGE = "mx-auto flex w-full max-w-[1328px] flex-col gap-4 px-4 py-4 md:px-6 md:py-6";
const TABS = ["skills", "fsp", "resume", "graph"] as const;
type Tab = (typeof TABS)[number];
const gradeLabel = (g: string) => GRADE[g] ?? GRADE_LABEL[g] ?? g;

/** Карточка с именем для скринридера и тестов: регион + заголовок. */
function Section({ title, label, aside, children, className, testid }: { title: string; label?: string; aside?: ReactNode; children: ReactNode; className?: string; testid: string }) {
  return (
    <Panel role="region" aria-label={label ?? title} data-testid={testid} className={cn("flex flex-col gap-3", className)}>
      <PanelCap title={title} aside={aside} className="mb-0" />
      {children}
    </Panel>
  );
}

function PdfButton({ name }: { name: string }) {
  const [state, setState] = useState<"idle" | "busy" | "error">("idle");
  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        variant="outline"
        size="sm"
        loading={state === "busy"}
        data-testid="profile-pdf"
        onClick={async () => {
          setState("busy");
          setState((await downloadProfilePdf(name)) ? "idle" : "error");
        }}
      >
        {state === "busy" ? T.pdfBusy : T.pdf}
      </Button>
      {state === "error" && (
        <p role="alert" className="text-13 text-error">
          {T.pdfError}
        </p>
      )}
    </div>
  );
}

/* ---------- Каркас: заголовок, действие, вкладки ---------- */

function Frame({ tab, children, bare }: { tab: Tab; children: ReactNode; bare?: boolean }) {
  return (
    <div className={PAGE} data-testid="profile-page" data-tab={tab}>
      <div className="flex flex-col gap-2.5 md:flex-row md:items-center md:justify-between">
        <H1 className="text-[22px] leading-[1.2] md:text-[26px]">{PROFILE.title}</H1>
        {!bare && (
          <Link to="/onboarding" className={cn(buttonVariants({ variant: "outline", size: "md" }), "hidden md:inline-flex")} data-testid="profile-add">
            {PROFILE.addEvidence}
          </Link>
        )}
      </div>
      {!bare && (
        <nav aria-label={PROFILE.tabsLabel} className="flex gap-0 overflow-x-auto border-b border-hairline md:gap-1" data-testid="profile-tabs">
          {TABS.map((k) => (
            <Link
              key={k}
              to={k === "skills" ? "/me/profile" : `/me/profile?tab=${k}`}
              replace
              aria-current={k === tab ? "page" : undefined}
              data-testid={`profile-tab-${k}`}
              className={cn(
                "-mb-px flex min-h-11 items-center whitespace-nowrap border-b-2 px-2 text-13 md:px-3.5 md:text-14",
                k === tab ? "border-brand font-semibold text-ink" : "border-transparent font-medium text-muted",
              )}
            >
              {PROFILE.tabs[k]}
            </Link>
          ))}
        </nav>
      )}
      {!bare && (
        <Link to="/onboarding" className={cn(buttonVariants({ size: "lg" }), "w-full md:hidden")} data-testid="profile-add-mobile">
          {PROFILE.addEvidence}
        </Link>
      )}
      {children}
    </div>
  );
}

/* ---------- Навыки ---------- */

function skillTags(s: SkillWithTrust): string[] {
  if (s.claimed_only) return [s.sources.includes("resume") ? PROFILE.claimedInResume : PROFILE.claimedSelf];
  const testEv = s.top_evidence?.find((e) => e.source === "test");
  const tags = ["test", "fsp", "github", "task", "resume"].filter((k) => s.sources.includes(k)).map((k) => (k === "test" ? PROFILE.testTag(dayMonth(testEv?.observed_at)) : SOURCE_TAG[k]));
  if (!tags.length) tags.push(s.derived_from ? PROFILE.derived : PROFILE.claimedSelf);
  return tags;
}

function SkillRows({ items }: { items: SkillWithTrust[] }) {
  return (
    <ul className="flex flex-col">
      {items.map((s) => (
        <li key={s.skill.slug} className="border-t border-hairline first:border-t-0">
          <Link to={`/me/skills/${encodeURIComponent(s.skill.slug)}`} aria-label={PROFILE.skillLink(s.skill.name)} className="flex min-h-11 items-center gap-3 py-2">
            <SkillTag name={s.skill.name} state={s.claimed_only ? "claimed" : "confirmed"} className="min-w-24" />
            <span aria-label={`доверие ${s.claimed_only ? 0 : Math.round(s.level)} из 4`} className="font-mono text-12 font-semibold tracking-[1px] text-brand-fg">
              {dotsText(s.claimed_only ? 0 : s.level)}
            </span>
            <Chips className="min-w-0 flex-1 justify-end">
              {skillTags(s).map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </Chips>
            <span aria-hidden className="text-muted">
              ›
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

function SkillsCard({ title, items, testid }: { title: string; items: SkillWithTrust[]; testid: string }) {
  if (!items.length) return null;
  return (
    <Section title={title} testid={testid} aside={<Num className="text-12 text-muted">{items.length}</Num>}>
      <SkillRows items={items} />
    </Section>
  );
}

function StatusCard({ p, standing }: { p: CandidateProfile; standing?: CandidateStanding }) {
  const confirmed = standing?.grade ?? null;
  const shown = confirmed ?? p.grade.grade ?? null;
  const role = standing?.profession ?? p.category?.primary_role;
  const until = p.active_until ? new Date(p.active_until) : null;
  return (
    <Panel role="region" aria-label={PROFILE.claimedAndConfirmed} data-testid="profile-status-card" className="flex flex-col gap-2.5">
      <Lbl>{PROFILE.claimedAndConfirmed}</Lbl>
      {shown ? (
        <>
          <Chips className="items-center">
            <GradeTag claimed={!confirmed} data-testid="profile-grade">
              {[gradeLabel(shown), role ? roleLabel(role) : null].filter(Boolean).join(" · ")}
            </GradeTag>
            <StatusTag state={confirmed ? "confirmed" : "claimed"} data-testid="profile-grade-status">
              {confirmed ? HOME.confirmed(dayMonth(standing?.confirmed_at), standing?.mode === "express") : HOME.notConfirmed}
            </StatusTag>
          </Chips>
          {!confirmed && p.grade.preliminary && (
            <p className="text-12 text-muted">
              {T.preliminary}
              {p.grade.confidence != null ? `, уверенность ${Math.round(p.grade.confidence * 100)}%` : ""}
            </p>
          )}
        </>
      ) : (
        <p className="text-14 text-muted">{T.noGrade}</p>
      )}
      <Chips>
        <StatusTag state={p.publishable === false ? "claimed" : "ok"} data-testid="profile-published">
          {p.publishable === false ? PROFILE.hidden : PROFILE.published}
        </StatusTag>
      </Chips>
      <p className="text-13 text-muted" data-testid="profile-status">
        <b className="font-semibold text-ink">{STATUS_LABEL[p.search_status]}</b>
        {p.search_status === "active" && until && <> до {until.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</>}
      </p>
      <p className="text-12 text-muted">{T.seenAs}</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <PdfButton name={p.pseudonym} />
        <Link to="/me/profile/edit" data-testid="profile-edit-link" className="inline-flex min-h-11 items-center font-semibold text-brand-fg">
          {T.editLink}
        </Link>
      </div>
    </Panel>
  );
}

/** Чек-лист «что усилит профиль»: что уже есть в данных, что добавить. Процент силы не считаем: формулы на бэкенде нет. */
function Strength({ p }: { p: CandidateProfile }) {
  const sources = new Set((p.skills ?? []).flatMap((s) => s.sources));
  const done: Record<string, boolean> = {
    resume: sources.has("resume") || (p.experience ?? []).length > 0,
    fsp: (p.fsp?.achievements.length ?? 0) + (p.fsp?.ranks.length ?? 0) > 0 || sources.has("fsp"),
    github: sources.has("github"),
    test: sources.has("test"),
  };
  if (STRENGTH_ITEMS.every((i) => done[i.key])) return null;
  return (
    <Section title={T.strengthTitle} testid="profile-strength" className="border-tint-200 bg-tint-50">
      <p className="text-14">{T.strengthHint}</p>
      <ul className="flex flex-col">
        {STRENGTH_ITEMS.map((i) => (
          <li key={i.key} data-testid={`profile-strength-${i.key}`} className="flex min-h-11 items-center justify-between gap-3">
            <span className="flex min-w-0 flex-col">
              <span className="text-14 font-semibold">{i.label}</span>
              <span className="text-13 text-muted">{i.hint}</span>
            </span>
            {done[i.key] ? (
              <Badge variant="success">{T.strengthDone}</Badge>
            ) : (
              <Link to={i.to} className="inline-flex min-h-11 items-center font-semibold text-brand-fg" aria-label={`${T.strengthTodo}: ${i.label}`}>
                {T.strengthTodo}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function GradeWhy({ g }: { g: GradeInfo }) {
  if (!g.breakdown.length && g.grade == null) return null;
  const max = Math.max(1, ...g.breakdown.map((b) => Math.abs(b.points)));
  return (
    <Section title="Почему такой грейд" testid="profile-grade-why">
      <p className="text-13 text-muted">Баллы за подтверждённые факты. Чем больше проверяемого, тем точнее грейд.</p>
      <ul className="flex flex-col">
        {g.breakdown.map((b) => (
          <li key={b.signal} className="grid min-h-9 grid-cols-[minmax(0,1fr)_72px_52px] items-center gap-3">
            <span className="text-14">{b.label}</span>
            <span aria-hidden className="h-2 overflow-hidden rounded-sm bg-tint-100">
              <i className="block h-full bg-brand" style={{ width: `${Math.max(0, (b.points / max) * 100)}%` }} />
            </span>
            <b className="text-right font-mono text-14">{points(b.points)}</b>
          </li>
        ))}
      </ul>
      {g.score != null && g.grade && (
        <p className="mt-1 flex items-baseline justify-between border-t border-hairline pt-3">
          <span className="font-semibold">Итого</span>
          <span className="font-mono text-18 font-bold">
            {String(Math.round(g.score * 10) / 10).replace(".", ",")} → {GRADE_LABEL[g.grade] ?? g.grade}
          </span>
        </p>
      )}
      {g.next_grade && (
        <div className="rounded-lg border border-tint-100 bg-tint-50 p-3 text-14">
          <p>
            До уровня <b>{GRADE_LABEL[g.next_grade.grade] ?? g.next_grade.grade}</b> не хватает{" "}
            <b className="font-mono">{String(g.next_grade.points_needed).replace(".", ",")}</b> балла
          </p>
          {g.next_grade.hints.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-muted">
              {g.next_grade.hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <Link to="/me/assessment" className="inline-flex min-h-11 items-center self-start font-semibold text-brand-fg">
        Пройти тест и уточнить грейд
      </Link>
    </Section>
  );
}

function Claimed({ p }: { p: CandidateProfile }) {
  const rows = p.claimed_vs_confirmed ?? [];
  if (!rows.length) return null;
  const g = (v?: string | null) => (v ? (GRADE_LABEL[v] ?? v) : "нет");
  return (
    <Section title={T.claimedTitle} testid="profile-claimed">
      <p className="text-13 text-muted">{T.claimedHint}</p>
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.profession} data-testid={`profile-claimed-${r.profession}`} className="flex flex-col gap-1 border-t border-hairline pt-2 first:border-t-0 first:pt-0">
            <span className="flex flex-wrap items-baseline justify-between gap-2">
              <b className="font-mono text-14">{roleLabel(r.profession)}</b>
              <Badge variant={r.status === "confirmed" ? "success" : r.status === "overclaimed" ? "warning" : "muted"}>{CLAIM_STATUS_LABEL[r.status]}</Badge>
            </span>
            <span className="text-13 text-muted">
              заявлено: {g(r.declared_grade ?? r.resume_grade)} · по тесту: {g(r.confirmed_grade)}
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function TeamSignals({ p }: { p: CandidateProfile }) {
  const signals = p.team_signals ?? [];
  const soft = p.claimed_soft ?? [];
  if (!signals.length && !soft.length) return null;
  return (
    <Section title="Командные сигналы" testid="profile-team">
      {signals.map((t) => (
        <TeamSignalRow
          key={t.signal}
          name={SIGNAL_LABEL[t.signal] ?? t.signal}
          strength={t.label === "strong" ? "strong" : "medium"}
          fact={t.facts.map((f) => f.title).join("; ") || undefined}
        />
      ))}
      {soft.length > 0 && (
        <div className={cn(signals.length > 0 && "border-t border-dashed border-hairline pt-3")}>
          <TeamSignalRow name={soft.join(", ")} claimed />
        </div>
      )}
    </Section>
  );
}

function SkillsTab({ p, standing }: { p: CandidateProfile; standing?: CandidateStanding }) {
  const skills = sortSkills(p.skills ?? []);
  const confirmed = skills.filter((s) => !s.claimed_only);
  const claimed = skills.filter((s) => s.claimed_only);
  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-12 lg:items-start" data-testid="profile-skills">
      <div className="order-2 flex flex-col gap-4 lg:order-none lg:col-span-8">
        <SkillsCard title={PROFILE.confirmed} items={confirmed} testid="profile-skills-confirmed" />
        <SkillsCard title={PROFILE.claimed} items={claimed} testid="profile-skills-claimed" />
        <GradeWhy g={p.grade} />
        <Claimed p={p} />
        <TeamSignals p={p} />
      </div>
      <div className="order-1 flex flex-col gap-4 lg:order-none lg:col-span-4">
        <StatusCard p={p} standing={standing} />
        <Strength p={p} />
      </div>
    </div>
  );
}

/* ---------- ФСП ---------- */

function FspTab({ p, imported }: { p: CandidateProfile; imported: boolean }) {
  const items = p.fsp?.achievements ?? [];
  const ranks = p.fsp?.ranks ?? [];
  const placed: FspResult[] = items
    .filter((a) => a.place != null)
    .map((a) => ({
      discipline: FSP_LEVEL_LABEL[a.level] ?? a.level,
      tournament: a.title,
      place: a.place as number,
      total: a.of ?? undefined,
      role: a.team_role ? (TEAM_ROLE_LABEL[a.team_role] ?? a.team_role) : undefined,
      year: a.year,
    }));
  const unplaced = items.filter((a) => a.place == null);
  const linked = Boolean(p.fsp?.verified);
  return (
    <div className="flex flex-col gap-4" data-testid="profile-fsp-tab">
      <Section
        title={PROFILE.fspTitle}
        label="Достижения ФСП"
        testid="profile-fsp"
        aside={<StatusTag state={linked ? "ok" : "claimed"}>{linked ? PROFILE.fspLinked : PROFILE.fspNotLinked}</StatusTag>}
      >
        {items.length === 0 && ranks.length === 0 ? (
          <p className="text-14 text-muted">{T.fspEmpty}</p>
        ) : (
          <>
            {placed.length > 0 && <FspProtocol results={placed} />}
            {unplaced.length > 0 && (
              <ul className="flex flex-col gap-1">
                {unplaced.map((a) => (
                  <li key={a.fact_id} className="text-14">
                    {a.title} <span className="font-mono text-12 text-muted">· {a.year}</span>
                  </li>
                ))}
              </ul>
            )}
            {ranks.length > 0 && (
              <ul className="flex flex-wrap gap-2 border-t border-hairline pt-3">
                {ranks.map((r) => (
                  <li key={r.discipline}>
                    <Badge>
                      {RANK_LABEL[r.rank] ?? r.rank} · {DISCIPLINE_LABEL[r.discipline] ?? r.discipline}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
        {imported && (
          <p role="status" className="text-14 font-semibold text-brand-fg">
            {T.fspImported}
          </p>
        )}
        <FspLinkPanel next="/me/profile?tab=fsp" />
      </Section>
    </div>
  );
}

/* ---------- Резюме ---------- */

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-h-11 items-center gap-3 border-t border-hairline py-2.5 first:border-t-0 first:pt-0">
      <Lbl className="w-24 flex-none">{label}</Lbl>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

function ResumeTab({ p }: { p: CandidateProfile }) {
  const pref = p.preferences;
  const formats = formatsText(pref.formats ?? []);
  const months = p.experience_months;
  const exp = p.experience ?? [];
  const roles = (p.desired_roles ?? []).map(roleLabel);
  const none = <StatusTag state="claimed">{PROFILE.notSpecified}</StatusTag>;
  return (
    <div className="flex flex-col gap-4" data-testid="profile-resume">
      <Section title={PROFILE.resume} label="Резюме" testid="profile-resume-card">
        <div>
          <Row label={PROFILE.city}>{pref.city ? <Num className="text-14">{pref.city}</Num> : none}</Row>
          <Row label={PROFILE.salary}>{pref.salary_min != null ? <Num className="text-14">{PROFILE.salaryFrom(formatRub(pref.salary_min))}</Num> : none}</Row>
          <Row label={PROFILE.format}>{formats ? <Num className="text-14">{formats.toLowerCase()}</Num> : none}</Row>
          <Row label={PROFILE.experience}>{months != null ? <Num className="text-14">{PROFILE.experienceMonths(months)}</Num> : none}</Row>
          {roles.length > 0 && (
            <Row label={PROFILE.roles}>
              <Num className="text-14">{roles.join(", ")}</Num>
            </Row>
          )}
        </div>
        <Link to="/me/profile/edit" data-testid="profile-edit-link" className="inline-flex min-h-11 items-center self-start font-semibold text-brand-fg">
          {T.editLink}
        </Link>
      </Section>
      {exp.length > 0 && (
        <Section title="Опыт" testid="profile-experience">
          <ul className="flex flex-col gap-3">
            {exp.map((e, i) => (
              <li key={`${e.title}-${i}`} className="flex flex-col gap-0.5">
                <span className="font-semibold">{e.title}</span>
                <span className="text-14 text-muted">{[e.company, periodRu(e.start, e.end)].filter(Boolean).join(" · ")}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

/**
 * Профиль кандидата `/me/profile` (E38-6, макеты v2_me-profile__*, бриф §6.7): вкладки «Навыки · ФСП · Резюме · Граф»
 * (`?tab=`), «Подтверждено» и «Заявлено» отдельно, справа статус и грейд. Граф — бывший `/me/graph`.
 */
export default function Profile() {
  const [sp] = useSearchParams();
  const raw = sp.get("tab");
  const tab: Tab = TABS.includes(raw as Tab) ? (raw as Tab) : "skills";
  if (tab === "graph")
    return (
      <Frame tab={tab}>
        <GraphView />
      </Frame>
    );
  return <ProfileData tab={tab} />;
}

function ProfileData({ tab }: { tab: Tab }) {
  const q = useGetProfileCandidatesMeProfileGet();
  const sq = useMyStandingCandidatesMeStandingGet({ query: { retry: false } });
  const [imported, setImported] = useState(false);
  useEventStream(() => setImported(true), ["fsp.imported"]);

  if (q.isPending)
    return (
      <Frame tab={tab} bare>
        <div className="flex flex-col gap-3" data-testid="profile-loading">
          <p role="status" className="sr-only">
            {PROFILE.loading}
          </p>
          <div className="grid gap-4 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-40" />
            ))}
          </div>
        </div>
      </Frame>
    );
  if (q.isError || q.data.status !== 200) {
    const status = q.error?.status;
    return (
      <Frame tab={tab} bare>
        <div className="w-full max-w-2xl" data-testid="profile-error">
          <ErrorState title={PROFILE.loadError} code={status ? PROFILE.errorCode(status) : undefined} onRetry={() => void q.refetch()} />
        </div>
      </Frame>
    );
  }
  const p = q.data.data;
  const standing = sq.data?.status === 200 ? sq.data.data : undefined;
  const empty = !(p.skills ?? []).length && !(p.fsp?.achievements.length) && !(p.fsp?.ranks.length) && !p.grade.grade;
  if (empty && tab === "skills")
    return (
      <Frame tab={tab} bare>
        <EmptyState
          className="min-h-[200px]"
          title={PROFILE.empty}
          description={T.noGrade}
          action={
            <Link to="/onboarding" className={buttonVariants({ size: "lg" })} data-testid="profile-empty-action">
              {PROFILE.addEvidence}
            </Link>
          }
        />
      </Frame>
    );
  return (
    <Frame tab={tab}>
      {tab === "skills" && <SkillsTab p={p} standing={standing} />}
      {tab === "fsp" && <FspTab p={p} imported={imported} />}
      {tab === "resume" && <ResumeTab p={p} />}
    </Frame>
  );
}
