import { Link } from "react-router-dom";

import { useGetProfileCandidatesMeProfileGet } from "@/api/endpoints/candidates/candidates";
import type { CandidateProfile, ExperienceItem, GradeInfo, OwnerFsp, SkillWithTrust, TeamSignal } from "@/api/model";
import { Button } from "@/shared/ui/button";
import { ErrorNote } from "@/features/auth/ui";
import {
  DISCIPLINE_LABEL,
  dots,
  FSP_LEVEL_LABEL,
  GRADE_LABEL,
  periodRu,
  RANK_LABEL,
  TEAM_ROLE_LABEL,
  points,
  roleLabel,
  SIGNAL_LABEL,
  STATUS_LABEL,
  STRENGTH_LABEL,
} from "@/features/profile/text";
import { ConstellationAvatar, SkillChip, type TrustKind } from "@/shared/brand";
import { cn } from "@/shared/lib/cn";

function Card({ title, label, children, className }: { title: string; label?: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={label ?? title} className={cn("flex flex-col gap-3 rounded-xl border border-hairline bg-card p-5", className)}>
      <h2 className="font-mono text-[17px] font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function kindOf(s: SkillWithTrust): TrustKind {
  if (s.claimed_only) return "claimed";
  if (s.derived_from) return "inferred";
  if (s.status === "provisional") return "provisional";
  return "verified";
}

function Header({ p }: { p: CandidateProfile }) {
  const g = p.grade;
  const parts = [
    g.grade ? (GRADE_LABEL[g.grade] ?? g.grade) : null,
    p.category ? roleLabel(p.category.primary_role) : null,
    p.category?.primary_stack[0] ?? null,
  ].filter(Boolean);
  const until = p.active_until ? new Date(p.active_until) : null;
  return (
    <section aria-label="Шапка профиля" className="flex flex-col gap-4 rounded-xl border border-hairline bg-card p-5">
      <div className="flex items-center gap-4">
        <ConstellationAvatar seed={p.pseudonym} size={72} />
        <div className="flex min-w-0 flex-col gap-0.5">
          <h2 className="break-words font-mono text-2xl font-semibold">{p.pseudonym}</h2>
          <span className="text-[13px] text-muted">Так вас видят компании, пока вы не примете оффер</span>
        </div>
      </div>
      {parts.length > 0 ? (
        <div className="flex flex-col items-start gap-1.5">
          <span
            className={cn(
              "inline-flex h-[30px] items-center rounded-md px-3 font-mono text-[13px] font-semibold",
              g.preliminary ? "border border-dashed border-brand-fg text-brand-fg" : "bg-brand text-on-brand",
            )}
          >
            {parts.join(" · ")}
          </span>
          {g.preliminary && (
            <span className="text-xs text-muted">
              Предварительно: пока мало подтверждённых фактов
              {g.confidence != null ? `, уверенность ${Math.round(g.confidence * 100)}%` : ""}
            </span>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted">Категория и грейд появятся, когда в профиле будут навыки: загрузите резюме или подключите ФСП.</p>
      )}
      <p className="flex items-center gap-2 rounded-lg border border-hairline px-4 py-3 text-sm">
        <b className="font-semibold">{STATUS_LABEL[p.search_status]}</b>
        {p.search_status === "active" && until && (
          <span className="font-mono text-[13px]">
            до {until.toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}
          </span>
        )}
      </p>
    </section>
  );
}

function GradeWhy({ g }: { g: GradeInfo }) {
  if (!g.breakdown.length && g.grade == null) return null;
  const max = Math.max(1, ...g.breakdown.map((b) => Math.abs(b.points)));
  return (
    <Card title="Почему такой грейд" label="Почему такой грейд">
      <p className="text-[13px] text-muted">Баллы за подтверждённые факты. Чем больше проверяемого, тем точнее грейд.</p>
      <ul className="flex flex-col">
        {g.breakdown.map((b) => (
          <li key={b.signal} className="grid min-h-9 grid-cols-[minmax(0,1fr)_72px_52px] items-center gap-3">
            <span className="text-sm">{b.label}</span>
            <span aria-hidden className="h-2 overflow-hidden rounded-sm bg-tint-100">
              <i className="block h-full bg-brand" style={{ width: `${Math.max(0, (b.points / max) * 100)}%` }} />
            </span>
            <b className="text-right font-mono text-sm">{points(b.points)}</b>
          </li>
        ))}
      </ul>
      {g.score != null && g.grade && (
        <p className="mt-1 flex items-baseline justify-between border-t border-hairline pt-3">
          <span className="font-semibold">Итого</span>
          <span className="font-mono text-lg font-bold">
            {String(Math.round(g.score * 10) / 10).replace(".", ",")} → {GRADE_LABEL[g.grade] ?? g.grade}
          </span>
        </p>
      )}
      {g.next_grade && (
        <div className="rounded-lg border border-tint-100 bg-tint-50 p-3 text-sm">
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
    </Card>
  );
}

function Skills({ skills }: { skills: SkillWithTrust[] }) {
  return (
    <Card title="Навыки">
      {skills.length === 0 ? (
        <p className="text-sm text-muted">Пока нет навыков. Загрузите резюме или подключите ФСП, и они появятся здесь.</p>
      ) : (
        <>
          <ul className="flex flex-wrap gap-2">
            {skills.map((s) => (
              <li key={s.skill.slug}>
                <Link to={`/me/skills/${encodeURIComponent(s.skill.slug)}`} aria-label={`${s.skill.name}: чем подтверждён`} className="rounded-md">
                  <SkillChip name={s.skill.name} level={s.claimed_only ? 0 : dots(s.level)} variant={kindOf(s)} />
                </Link>
              </li>
            ))}
          </ul>
          <p className="text-[13px] text-muted">
            Нажмите на навык, чтобы увидеть, чем он подтверждён. Пунктир — заявлено или выведено, без доказательств сила не растёт.
          </p>
        </>
      )}
    </Card>
  );
}

function TeamSignals({ signals, soft }: { signals: TeamSignal[]; soft: string[] }) {
  if (!signals.length && !soft.length) return null;
  return (
    <Card title="Командные сигналы">
      {signals.map((t) => (
        <div key={t.signal} className="flex flex-col gap-0.5">
          <div className="flex flex-wrap items-baseline gap-2">
            <span className="font-semibold">{SIGNAL_LABEL[t.signal] ?? t.signal}</span>
            <span className="font-mono text-xs font-semibold text-brand-fg">— {STRENGTH_LABEL[t.label] ?? t.label}</span>
          </div>
          {t.facts.map((f, i) => (
            <span key={f.fact_id ?? i} className="text-sm text-muted">
              {f.title}
            </span>
          ))}
        </div>
      ))}
      {soft.length > 0 && (
        <div className={cn("flex flex-col gap-0.5", signals.length > 0 && "border-t border-dashed border-hairline pt-3")}>
          <span className="text-sm text-muted">
            <b className="font-semibold">Указано в резюме:</b> {soft.join(", ")}
          </span>
          <span className="font-mono text-[11px] text-muted">не влияет на грейд</span>
        </div>
      )}
    </Card>
  );
}


function FspCard({ fsp }: { fsp?: OwnerFsp | null }) {
  const items = fsp?.achievements ?? [];
  const ranks = fsp?.ranks ?? [];
  return (
    <Card title="Достижения ФСП">
      {items.length === 0 && ranks.length === 0 ? (
        <p className="text-sm text-muted">
          Результатов ФСП пока нет. Когда профиль будет связан с ФСП, соревнования и разряды появятся здесь и усилят грейд.
        </p>
      ) : (
        <>
          <ul className="flex flex-col gap-3">
            {items.map((a) => (
              <li key={a.fact_id} className="grid grid-cols-[44px_minmax(0,1fr)] items-start gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-tint-100 font-mono text-lg font-bold text-brand-deep dark:text-brand-mid">
                  {a.place ?? "·"}
                </span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="break-words text-sm font-semibold">{a.title}</span>
                  <span className="font-mono text-xs text-muted">
                    {[
                      a.place != null && a.of != null ? `${a.place} из ${a.of}` : null,
                      FSP_LEVEL_LABEL[a.level] ?? null,
                      a.team_role ? TEAM_ROLE_LABEL[a.team_role] ?? a.team_role : null,
                      a.year,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          {ranks.length > 0 && (
            <ul className="flex flex-wrap gap-2 border-t border-hairline pt-3">
              {ranks.map((r) => (
                <li key={r.discipline} className="rounded-md border border-tint-200 bg-tint-50 px-2.5 py-1 text-xs font-semibold text-brand-deep dark:text-brand-mid">
                  {RANK_LABEL[r.rank] ?? r.rank} · {DISCIPLINE_LABEL[r.discipline] ?? r.discipline}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}

function ExperienceCard({ items }: { items: ExperienceItem[] }) {
  if (!items.length) return null;
  return (
    <Card title="Опыт">
      <ul className="flex flex-col gap-3">
        {items.map((e, i) => (
          <li key={`${e.title}-${i}`} className="flex flex-col gap-0.5">
            <span className="font-semibold">{e.title}</span>
            <span className="text-sm text-muted">{[e.company, periodRu(e.start, e.end)].filter(Boolean).join(" · ")}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function NextStep({ p }: { p: CandidateProfile }) {
  const verified = (p.skills ?? []).filter((s) => !s.claimed_only).length;
  if (verified >= 3 && p.grade.grade) return null;
  return (
    <section aria-label="Усилить профиль" className="flex flex-col gap-3 rounded-xl border border-tint-200 bg-tint-50 p-5">
      <h2 className="font-mono text-[17px] font-semibold">Усильте профиль</h2>
      <p className="text-sm">
        Чем больше проверяемого в профиле, тем выше доверие к навыкам и точнее грейд. Загрузите резюме: навыки появятся с цитатами из текста.
      </p>
      <Link to="/onboarding" className="self-start">
        <Button size="sm">Загрузить резюме</Button>
      </Link>
    </section>
  );
}

/** «Мой профиль» (макет D): шапка, почему такой грейд, навыки с точками, командные сигналы. */
export default function Profile() {
  const q = useGetProfileCandidatesMeProfileGet();
  const title = <h1 className="sr-only">Мой профиль</h1>;
  if (q.isPending)
    return (
      <>
        {title}
        <p role="status" className="text-muted">Загрузка профиля…</p>
      </>
    );
  if (q.isError)
    return (
      <>
        {title}
        <ErrorNote>Не удалось загрузить профиль. Обновите страницу.</ErrorNote>
      </>
    );
  const p = q.data.data;
  return (
    <div className="mx-auto grid w-full max-w-5xl items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {title}
      <div className="flex min-w-0 flex-col gap-4">
        <Header p={p} />
        <NextStep p={p} />
        <GradeWhy g={p.grade} />
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        <Skills skills={p.skills ?? []} />
        <FspCard fsp={p.fsp} />
        <TeamSignals signals={p.team_signals ?? []} soft={p.claimed_soft ?? []} />
        <ExperienceCard items={p.experience ?? []} />
      </div>
    </div>
  );
}
