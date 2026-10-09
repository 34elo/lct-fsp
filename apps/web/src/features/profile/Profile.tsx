import { PAGE } from "@/shared/lib/page";
import type { GlossaryKey } from "@/shared/glossary";
import { Gi, Gloss } from "@/shared/Gloss";
import {
  Badge,
  Button,
  Chips,
  EmptyState,
  ErrorState,
  GradeTag,
  H1,
  H2,
  Lbl,
  MetricTile,
  Panel,
  PanelCap,
  ScrollTabs,
  SkeletonProfile,
  StatusTag,
  Tabs,
  TabsContent,
  TabsTrigger,
  TeamSignal as TeamSignalRow,
  buttonVariants,
  cn,
} from "@fsp/ui";
import { useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { useGetProfileCandidatesMeProfileGet } from "@/api/endpoints/candidates/candidates";
import { useMyStandingCandidatesMeStandingGet } from "@/api/endpoints/search/search";
import type { CandidateProfile, CandidateStanding } from "@/api/model";
import { GRADE } from "@/features/assessment/text";
import GraphView from "@/features/graph/Graph";
import { downloadProfilePdf } from "@/features/profile/pdf";
import { dayMonth } from "./home-model";
import { DataTab } from "./ProfileData";
import { SkillsTab } from "./ProfileSkills";
import { CLAIM_STATUS_LABEL, GRADE_LABEL, HOME, PROFILE, SIGNAL_LABEL, STATUS_LABEL, STRENGTH_ITEMS, T, roleLabel } from "./text";
import { useEventStream } from "@/shared/lib/useEventStream";

const TABS = ["overview", "skills", "data", "graph"] as const;
/** Старые вкладки «ФСП» и «Резюме» (до E39-15) слились в «Данные». */
const LEGACY: Record<string, Tab> = { fsp: "data", resume: "data" };
type Tab = (typeof TABS)[number];
const gradeLabel = (g: string) => GRADE[g] ?? GRADE_LABEL[g] ?? g;

/** Карточка с именем для скринридера и тестов: регион + заголовок. */
function Section({ title, tip, label, aside, children, className, testid }: { title: string; tip?: GlossaryKey; label?: string; aside?: ReactNode; children: ReactNode; className?: string; testid: string }) {
  return (
    <Panel role="region" aria-label={label ?? title} data-testid={testid} className={cn("flex flex-col gap-3", className)}>
      <PanelCap title={tip ? <Gloss k={tip}><H2>{title}</H2></Gloss> : title} aside={aside} className="mb-0" />
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

/* ---------- Каркас: заголовок и вкладки ---------- */

function Frame({ tab, children, tabs = true }: { tab: Tab; children: ReactNode; tabs?: boolean }) {
  const [, setSp] = useSearchParams();
  return (
    <div className={PAGE.normal} data-testid="profile-page" data-tab={tab}>
      <H1 className="text-[22px] leading-[1.2] md:text-[26px]">{PROFILE.title}</H1>
      {tabs ? (
        <Tabs value={tab} onValueChange={(v) => setSp(v === "overview" ? {} : { tab: v }, { replace: true })}>
          <ScrollTabs aria-label={PROFILE.tabsLabel} data-testid="profile-tabs">
            {TABS.map((k) => (
              <TabsTrigger key={k} value={k} data-testid={`profile-tab-${k}`}>
                {PROFILE.tabs[k]}
              </TabsTrigger>
            ))}
          </ScrollTabs>
          <TabsContent value={tab} className="pt-4">
            {children}
          </TabsContent>
        </Tabs>
      ) : (
        children
      )}
    </div>
  );
}

function StatusCard({ p, standing }: { p: CandidateProfile; standing?: CandidateStanding }) {
  const confirmed = standing?.grade ?? null;
  const shown = confirmed ?? p.grade.grade ?? null;
  const role = standing?.profession ?? p.category?.primary_role;
  const until = p.active_until ? new Date(p.active_until) : null;
  return (
    <Panel role="region" aria-label={PROFILE.claimedAndConfirmed} data-testid="profile-status-card" className="flex flex-col gap-2.5">
      <Lbl>
        <Gloss k="claimed">{PROFILE.claimed}</Gloss> / <Gloss k="confirmed">{PROFILE.confirmed}</Gloss>
      </Lbl>
      {shown ? (
        <>
          <Chips className="items-center">
            <GradeTag claimed={!confirmed} data-testid="profile-grade">
              {[gradeLabel(shown), role ? roleLabel(role) : null].filter(Boolean).join(" · ")}
            </GradeTag>
            <StatusTag state={confirmed ? "confirmed" : "claimed"} data-testid="profile-grade-status">
              {confirmed ? HOME.confirmed(dayMonth(standing?.confirmed_at), standing?.mode === "express") : HOME.notConfirmed}
            </StatusTag>
            <Gi k="grade" />
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
        {/* Данные шага 1 потока до теста (E39-6) правятся здесь же: направление и навыки. */}
        <Link to="/me/assessment?step=1" data-testid="profile-direction-link" className="inline-flex min-h-11 items-center font-semibold text-brand-fg">
          {T.directionLink}
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

/* ---------- Обзор: плитки на всю ширину ---------- */

function Tiles({ p }: { p: CandidateProfile }) {
  const skills = p.skills ?? [];
  const fsp = (p.fsp?.achievements.length ?? 0) + (p.fsp?.ranks.length ?? 0);
  const tiles = [
    { key: "confirmed", label: PROFILE.tiles.confirmed, value: skills.filter((s) => !s.claimed_only).length, to: "/me/profile?tab=skills" },
    { key: "claimed", label: PROFILE.tiles.claimed, value: skills.filter((s) => s.claimed_only).length, to: "/me/profile?tab=skills" },
    { key: "fsp", label: PROFILE.tiles.fsp, value: fsp, to: "/me/profile?tab=data" },
  ];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3" data-testid="profile-tiles">
      {tiles.map((t) => (
        <Link key={t.key} to={t.to} className="rounded-2xl focus-visible:outline-2 focus-visible:outline-brand" data-testid={`profile-tile-${t.key}`}>
          <MetricTile label={t.label} value={t.value} className="h-full" />
        </Link>
      ))}
    </div>
  );
}

function OverviewTab({ p, standing }: { p: CandidateProfile; standing?: CandidateStanding }) {
  return (
    <div className="flex flex-col gap-4" data-testid="profile-overview">
      <StatusCard p={p} standing={standing} />
      <Tiles p={p} />
      <Strength p={p} />
      <Claimed p={p} />
      <TeamSignals p={p} />
    </div>
  );
}

/**
 * Профиль кандидата `/me/profile` (E38-6, переработан в E39-15): вкладки `ScrollTabs` «Обзор · Навыки · Данные ·
 * Граф» (`?tab=`). Обзор — грейд и статус, плитки, что усилит профиль, заявлено и подтверждено, командные
 * сигналы; Навыки — список с поиском и фильтрами; Данные — ФИО, контакты, опыт, образование, ссылки и ФСП;
 * Граф — `EvidenceGraph`. Старые адреса `?tab=fsp|resume` ведут в «Данные».
 */
export default function Profile() {
  const [sp] = useSearchParams();
  const raw = sp.get("tab") ?? "";
  const tab: Tab = (TABS as readonly string[]).includes(raw) ? (raw as Tab) : LEGACY[raw] ?? "overview";
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
      <Frame tab={tab}>
        <div data-testid="profile-loading">
          <p role="status" className="sr-only">
            {PROFILE.loading}
          </p>
          <SkeletonProfile />
        </div>
      </Frame>
    );
  if (q.isError || q.data.status !== 200) {
    const status = q.error?.status;
    return (
      <Frame tab={tab} tabs={false}>
        <div className="w-full max-w-2xl" data-testid="profile-error">
          <ErrorState title={PROFILE.loadError} code={status ? PROFILE.errorCode(status) : undefined} onRetry={() => void q.refetch()} />
        </div>
      </Frame>
    );
  }
  const p = q.data.data;
  const standing = sq.data?.status === 200 ? sq.data.data : undefined;
  const empty = !(p.skills ?? []).length && !p.fsp?.achievements.length && !p.fsp?.ranks.length && !p.grade.grade;
  return (
    <Frame tab={tab}>
      {tab === "overview" &&
        (empty ? (
          <EmptyState
            className="min-h-[200px]"
            title={PROFILE.empty}
            description={T.noGrade}
            action={
              <Link to="/me/assessment" className={buttonVariants({ size: "lg" })} data-testid="profile-empty-action">
                {PROFILE.emptyAction}
              </Link>
            }
          />
        ) : (
          <OverviewTab p={p} standing={standing} />
        ))}
      {tab === "skills" && <SkillsTab p={p} />}
      {tab === "data" && <DataTab p={p} imported={imported} />}
    </Frame>
  );
}
