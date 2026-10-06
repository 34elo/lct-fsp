import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FspProtocol,
  GradeBadge,
  SectionLabel,
  Skeleton,
  TeamSignal as TeamSignalRow,
  type FspResult,
} from "@fsp/ui";

import { useGetProfileCandidatesMeProfileGet } from "@/api/endpoints/candidates/candidates";
import type { CandidateProfile, ExperienceItem, GradeInfo, OwnerFsp, SkillWithTrust, TeamSignal } from "@/api/model";
import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";
import { downloadProfilePdf } from "@/features/profile/pdf";
import {
  CLAIM_STATUS_LABEL,
  DISCIPLINE_LABEL,
  dots,
  FSP_LEVEL_LABEL,
  GRADE_LABEL,
  GROUP_LABEL,
  periodRu,
  points,
  RANK_LABEL,
  roleLabel,
  SIGNAL_LABEL,
  STATUS_LABEL,
  STRENGTH_ITEMS,
  T,
  TEAM_ROLE_LABEL,
} from "@/features/profile/text";
import { ConstellationAvatar, SkillChip, type TrustKind } from "@/shared/brand";
import { cn } from "@/shared/lib/cn";
import { useEventStream } from "@/shared/lib/useEventStream";

function Section({ title, label, children, className, testid }: { title: string; label?: string; children: React.ReactNode; className?: string; testid: string }) {
  return (
    <Card role="region" aria-label={label ?? title} data-testid={testid} className={cn("flex flex-col gap-3 p-5", className)}>
      <h2 className="font-mono text-17 font-semibold">{title}</h2>
      {children}
    </Card>
  );
}

function kindOf(s: SkillWithTrust): TrustKind {
  if (s.claimed_only) return "claimed";
  if (s.derived_from) return "inferred";
  if (s.status === "provisional") return "provisional";
  return "verified";
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

function Header({ p }: { p: CandidateProfile }) {
  const g = p.grade;
  const until = p.active_until ? new Date(p.active_until) : null;
  return (
    <Card role="region" aria-label="Шапка профиля" data-testid="profile-header" className="flex flex-col gap-4 p-5">
      <div className="flex items-center gap-4">
        <ConstellationAvatar seed={p.pseudonym} size={72} />
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="break-words font-mono text-24 font-semibold">{p.pseudonym}</h2>
          <span className="text-13 text-muted">{T.seenAs}</span>
        </div>
      </div>
      {g.grade ? (
        <div className="flex flex-col items-start gap-1.5">
          <GradeBadge
            grade={GRADE_LABEL[g.grade] ?? g.grade}
            role={p.category ? roleLabel(p.category.primary_role) : undefined}
            stack={p.category?.primary_stack[0]}
            preliminary={g.preliminary}
            hint={g.next_grade?.hints[0]}
          />
          {g.preliminary && (
            <span className="text-12 text-muted">
              {T.preliminary}
              {g.confidence != null ? `, уверенность ${Math.round(g.confidence * 100)}%` : ""}
            </span>
          )}
        </div>
      ) : (
        <p className="text-14 text-muted">{T.noGrade}</p>
      )}
      <p className="flex items-center gap-2 rounded-lg border border-hairline px-4 py-3 text-14" data-testid="profile-status">
        <b className="font-semibold">{STATUS_LABEL[p.search_status]}</b>
        {p.search_status === "active" && until && (
          <span className="font-mono text-13">до {until.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</span>
        )}
      </p>
      <div className="flex flex-wrap gap-2">
        <PdfButton name={p.pseudonym} />
        <Link to="/me/profile/edit" data-testid="profile-edit-link" className="inline-flex min-h-11 items-center font-semibold text-brand-fg">
          {T.editLink}
        </Link>
        <Link to="/me/graph" data-testid="profile-graph-link">
          <Button variant="ghost" size="sm" tabIndex={-1}>
            {T.graph}
          </Button>
        </Link>
      </div>
    </Card>
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

/** Навыки, у которых после обновления выросла сила или которых раньше не было: они «загораются» волной. */
function useIgnited(skills: SkillWithTrust[]): Map<string, number> {
  const prev = useRef<Map<string, number> | null>(null);
  const out = useRef(new Map<string, number>());
  const sig = skills.map((s) => `${s.skill.slug}:${s.claimed_only ? 0 : s.level}`).join("|");
  const seen = useRef<string | null>(null);
  if (seen.current !== sig) {
    const cur = new Map(skills.map((s) => [s.skill.slug, s.claimed_only ? 0 : s.level] as const));
    const lit = new Map<string, number>();
    if (prev.current) {
      let i = 0;
      for (const [slug, lvl] of cur) if (lvl > (prev.current.get(slug) ?? -1) && lvl > 0) lit.set(slug, i++);
    }
    out.current = lit;
    prev.current = cur;
    seen.current = sig;
  }
  return out.current;
}

function groupSkills(skills: SkillWithTrust[]): [string, SkillWithTrust[]][] {
  const by = new Map<string, SkillWithTrust[]>();
  for (const s of skills) by.set(s.skill.group, [...(by.get(s.skill.group) ?? []), s]);
  const order = Object.keys(GROUP_LABEL);
  const rank = (k: string) => (order.includes(k) ? order.indexOf(k) : order.length);
  return [...by.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));
}

function Skills({ skills }: { skills: SkillWithTrust[] }) {
  const lit = useIgnited(skills);
  return (
    <Section title="Навыки" testid="profile-skills">
      {skills.length === 0 ? (
        <p className="text-14 text-muted">{T.skillsEmpty}</p>
      ) : (
        <>
          {groupSkills(skills).map(([group, items]) => (
            <div key={group} className="flex flex-col gap-2" data-testid={`profile-skill-group-${group}`}>
              <SectionLabel>{GROUP_LABEL[group] ?? "Другое"}</SectionLabel>
              <ul className="flex flex-wrap gap-2">
                {items.map((s) => (
                  <li
                    key={`${s.skill.slug}-${lit.has(s.skill.slug) ? "lit" : ""}`}
                    className={lit.has(s.skill.slug) ? "fsp-ignite rounded-md" : undefined}
                    style={lit.has(s.skill.slug) ? ({ "--i": lit.get(s.skill.slug) } as React.CSSProperties) : undefined}
                  >
                    <Link to={`/me/skills/${encodeURIComponent(s.skill.slug)}`} aria-label={`${s.skill.name}: чем подтверждён`} className="inline-flex min-h-11 items-center rounded-md sm:min-h-0">
                      <SkillChip name={s.skill.name} level={s.claimed_only ? 0 : dots(s.level)} variant={kindOf(s)} />
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <p className="text-13 text-muted">{T.skillsHint}</p>
        </>
      )}
    </Section>
  );
}

function TeamSignals({ signals, soft }: { signals: TeamSignal[]; soft: string[] }) {
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

function FspCard({ fsp, imported }: { fsp?: OwnerFsp | null; imported: boolean }) {
  const items = fsp?.achievements ?? [];
  const ranks = fsp?.ranks ?? [];
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
  return (
    <Section title="Достижения ФСП" testid="profile-fsp">
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
      <FspLinkPanel next="/me" />
    </Section>
  );
}

function ExperienceCard({ items }: { items: ExperienceItem[] }) {
  if (!items.length) return null;
  return (
    <Section title="Опыт" testid="profile-experience">
      <ul className="flex flex-col gap-3">
        {items.map((e, i) => (
          <li key={`${e.title}-${i}`} className="flex flex-col gap-0.5">
            <span className="font-semibold">{e.title}</span>
            <span className="text-14 text-muted">{[e.company, periodRu(e.start, e.end)].filter(Boolean).join(" · ")}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** «Мой профиль» (макет D): шапка, что усилит, почему такой грейд, навыки по группам, ФСП, командные сигналы. */
export default function Profile() {
  const q = useGetProfileCandidatesMeProfileGet();
  const [imported, setImported] = useState(false);
  useEventStream(() => setImported(true), ["fsp.imported"]);
  const title = <h1 className="sr-only">{T.title}</h1>;
  if (q.isPending)
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-4" data-testid="profile-loading">
        {title}
        <p role="status" className="sr-only">
          {T.loading}
        </p>
        <Skeleton className="h-52" />
        <Skeleton className="h-40" />
      </div>
    );
  if (q.isError || q.data.status !== 200)
    return (
      <div className="mx-auto w-full max-w-2xl">
        {title}
        <ErrorState title={T.loadError} description={T.loadErrorHint} onRetry={() => void q.refetch()} />
      </div>
    );
  const p = q.data.data;
  const empty = !p.grade.grade && !(p.skills ?? []).length;
  return (
    <div className="mx-auto grid w-full max-w-5xl items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]" data-testid="profile-page">
      {title}
      <div className="flex min-w-0 flex-col gap-4">
        <Header p={p} />
        <Strength p={p} />
        <GradeWhy g={p.grade} />
        <Claimed p={p} />
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        {empty && !(p.fsp?.achievements.length) ? (
          <EmptyState
            title="Профиль пока пуст"
            description="Загрузите резюме или подключите ФСП: навыки и грейд появятся сами."
            action={
              <Link to="/onboarding">
                <Button size="sm" tabIndex={-1}>
                  Загрузить резюме
                </Button>
              </Link>
            }
          />
        ) : null}
        <Skills skills={p.skills ?? []} />
        <FspCard fsp={p.fsp} imported={imported} />
        <TeamSignals signals={p.team_signals ?? []} soft={p.claimed_soft ?? []} />
        <ExperienceCard items={p.experience ?? []} />
      </div>
    </div>
  );
}
