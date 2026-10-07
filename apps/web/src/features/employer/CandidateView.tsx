import { Button, ConstellationAvatar, FspProtocol, GradeBadge, MatchRing, MatchWhy, SectionLabel, SkillChip, ThemeScope, VerifiedMark, type WhyItem } from "@fsp/ui";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { useCandidateCardCandidatesPseudoIdCardGet } from "@/api/endpoints/search/search";
import type { CandidateCardFull, SkillWithTrust } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { OfferDialog } from "@/features/offers/OfferDialog";
import { EMP_INT_TEXT as IT } from "@/features/offers/text";
import { GRADE_LABEL, points, roleLabel } from "@/features/profile/text";
import { cn } from "@/shared/lib/cn";
import { dedupeExperience, fspResults, groupSkills, kindOf, radarAxes, skillLevel, trustSources, yearsLabel, type SkillGroup } from "./candidate-model";
import { FORMAT_LABEL, percent, rub, SEARCH_STATUS_LABEL } from "./text";

const T = {
  back: "К подбору",
  header: "Шапка карточки",
  offer: "Отправить приглашение",
  offered: "Приглашение уже отправлялся",
  expectations: "Ожидания",
  skills: "Навыки",
  skillsHint: "нажмите на точки у навыка — откуда он",
  legendSolid: "Сплошной контур — подтверждено",
  legendDashed: "Пунктир — заявлено или выведено",
  noSkills: "Навыки ещё не подтверждены.",
  claimedMore: (n: number) => `ещё ${n} без подтверждения`,
  claimedNote: "Заявлены кандидатом, независимого подтверждения нет.",
  fsp: "Достижения ФСП",
  radar: "Профиль навыков",
  graph: "Граф доказательств",
  graphHint: "Какие факты подтверждают какие навыки и насколько сильно",
  graphSoon: "Интерактивный граф появится позже. Список ниже содержит те же связи.",
  graphList: "Показать связи списком",
  experience: "Опыт",
  experienceHint: "Названия компаний скрыты до раскрытия контактов",
  why: "Почему подходит",
  grade: "Грейд",
  next: "Следующий шаг",
  contacts: "Контакты откроются только после согласия кандидата.",
  notFound: "Кандидат не найден или скрыт.",
  loading: "Загрузка…",
};

const WHY_KIND = { plus: "ok", minus: "no", warn: "warn" } as const;

function Panel({ title, hint, children, className }: { title: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={title} className={cn("flex flex-col gap-3 rounded-xl border border-hairline bg-card p-5", className)}>
      <div className="flex flex-col gap-0.5">
        <h2 className="font-mono text-17 font-semibold">{title}</h2>
        {hint && <p className="text-13 text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Skills({ groups, claimed }: { groups: SkillGroup[]; claimed: SkillWithTrust[] }) {
  if (groups.length === 0 && claimed.length === 0) return <p className="text-sm text-muted">{T.noSkills}</p>;
  return (
    <div className="flex flex-col gap-4">
      {groups.map((g) => (
        <div key={g.label} className="flex flex-col gap-2">
          <SectionLabel>{g.label}</SectionLabel>
          <ul className="flex flex-wrap gap-2">
            {g.skills.map((s) => (
              <li key={s.skill.slug}>
                <SkillChip name={s.skill.name} variant={kindOf(s)} level={skillLevel(s)} sources={trustSources(s)} />
              </li>
            ))}
          </ul>
        </div>
      ))}
      {claimed.length > 0 && (
        <details className="text-13 text-muted">
          <summary className="cursor-pointer select-none font-medium text-ink">{T.claimedMore(claimed.length)}</summary>
          <p className="mt-2">{T.claimedNote}</p>
          <ul className="mt-2 flex flex-wrap gap-2">
            {claimed.map((s) => (
              <li key={s.skill.slug}>
                <SkillChip name={s.skill.name} variant="claimed" />
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="flex flex-wrap gap-x-4 gap-y-1 text-12 text-muted">
        <span>{T.legendSolid}</span>
        <span>{T.legendDashed}</span>
      </p>
    </div>
  );
}

/** Радар по группам навыков: SVG, максимальный уровень 0–4 в группе. */
function Radar({ axes }: { axes: { label: string; value: number }[] }) {
  if (axes.length < 3) return null;
  const R = 70;
  const C = 100;
  const pt = (i: number, v: number): string => {
    const a = (i / axes.length) * Math.PI * 2 - Math.PI / 2;
    return `${C + Math.cos(a) * R * (v / 4)},${C + Math.sin(a) * R * (v / 4)}`;
  };
  return (
    <figure className="flex flex-col items-center gap-2">
      <svg viewBox="0 0 200 200" role="img" aria-label={`${T.radar}: ${axes.map((a) => `${a.label} ${a.value} из 4`).join(", ")}`} className="size-48">
        {[1, 2, 3, 4].map((r) => (
          <polygon key={r} points={axes.map((_, i) => pt(i, r)).join(" ")} fill="none" className="stroke-hairline" strokeWidth={1} />
        ))}
        <polygon points={axes.map((a, i) => pt(i, a.value)).join(" ")} className="fill-brand/25 stroke-brand" strokeWidth={1.5} />
      </svg>
      <figcaption className="text-center text-12 text-muted">{axes.map((a) => a.label).join(" · ")}</figcaption>
    </figure>
  );
}

/** Место под EvidenceGraph (E16-3) и список связей для скринридеров. */
function EvidenceList({ skills }: { skills: SkillWithTrust[] }) {
  const withEv = skills.filter((s) => s.top_evidence.length > 0);
  return (
    <div className="flex flex-col gap-3">
      <p data-evidence-graph className="rounded-lg border border-dashed border-hairline p-4 text-13 text-muted">{T.graphSoon}</p>
      {withEv.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer select-none font-semibold">{T.graphList}</summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {withEv.map((s) => (
              <li key={s.skill.slug} className="text-13">
                <b className="font-mono">{s.skill.name}</b>
                <span className="text-muted"> ← {s.top_evidence.map((e) => e.title).join("; ")}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Body({ c, vacancyId }: { c: CandidateCardFull; vacancyId: string | null }) {
  const grade = c.grade ? (GRADE_LABEL[c.grade] ?? c.grade) : null;
  const items: WhyItem[] = (c.match?.explanation ?? []).map((i) => ({ kind: WHY_KIND[i.kind], text: i.text }));
  const offered = c.offers_from_you.length > 0;
  const [offerOpen, setOfferOpen] = useState(false);
  const [interestOpen, setInterestOpen] = useState(false);
  const { groups, claimed } = groupSkills(c.skills);
  const protocol = fspResults(c.fsp_highlights);
  const experience = dedupeExperience(c.experience);
  const meta = [c.city, c.relocation ? "готов к релокации" : null, c.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", "), SEARCH_STATUS_LABEL[c.search_status]].filter(Boolean).join(" · ");
  return (
    <div className="flex flex-col gap-4">
      <section aria-label={T.header} className="flex flex-col gap-4 rounded-xl border border-hairline bg-card p-5 md:flex-row md:items-center">
        <ConstellationAvatar seed={c.avatar_seed} size={72} />
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <h1 className="break-words font-mono text-2xl font-semibold">{c.pseudonym}</h1>
          <div className="flex flex-wrap items-center gap-2">
            {grade && <GradeBadge grade={grade} role={c.primary_role ? roleLabel(c.primary_role) : undefined} stack={c.primary_stack.slice(0, 2).join(", ") || undefined} preliminary={c.grade_preliminary} />}
            {protocol.length > 0 && <VerifiedMark />}
            {c.interested_you && <span className="inline-flex items-center rounded-full border border-brand bg-tint-50 px-2.5 py-0.5 text-12 font-semibold text-brand-fg">{IT.interestedYou}</span>}
          </div>
          <p className="text-13 text-muted">
            {[c.salary_min ? `${T.expectations} от ${rub(c.salary_min)}` : null, meta].filter(Boolean).join(" · ")}
          </p>
        </div>
        {c.match && <MatchRing value={percent(c.match.score)} size={72} />}
        <div className="flex flex-col gap-1">
          <Button onClick={() => setOfferOpen(true)}>{T.offer}</Button>
          <Button variant="outline" onClick={() => setInterestOpen(true)}>{IT.interestBtn}</Button>
          <OfferDialog
            open={interestOpen}
            onOpenChange={setInterestOpen}
            dark
            mode="interest"
            candidate={{ pseudoId: c.pseudo_id, pseudonym: c.pseudonym, salaryMin: c.salary_min ?? null }}
            vacancyId={vacancyId ?? ""}
          />
          <OfferDialog
            open={offerOpen}
            onOpenChange={setOfferOpen}
            dark
            candidate={{ pseudoId: c.pseudo_id, pseudonym: c.pseudonym, salaryMin: c.salary_min ?? null }}
            vacancyId={vacancyId ?? ""}
            alreadyOffered={offered}
          />
          {offered && (
            <span className="text-xs text-muted">
              {T.offered}: {c.offers_from_you.map((o) => o.status).join(", ")}
            </span>
          )}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-4">
          <Panel title={T.skills} hint={T.skillsHint}>
            <Skills groups={groups} claimed={claimed} />
          </Panel>
          {protocol.length > 0 && (
            <Panel title={T.fsp}>
              <FspProtocol results={protocol} />
            </Panel>
          )}
          <Panel title={T.graph} hint={T.graphHint}>
            <Radar axes={radarAxes(groups)} />
            <EvidenceList skills={groups.flatMap((g) => g.skills)} />
          </Panel>
          {experience.length > 0 && (
            <Panel title={T.experience} hint={T.experienceHint}>
              <ul className="flex flex-col gap-2 text-sm">
                {experience.map((e, n) => (
                  <li key={n} className="flex flex-col">
                    <b className="font-semibold">{e.title ?? "Роль не указана"}</b>
                    {e.skills.length > 0 && <span className="text-13 text-muted">{e.skills.join(", ")}</span>}
                    <span className="font-mono text-12 text-muted">{yearsLabel(e.months)}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-4">
          {items.length > 0 && (
            <Panel title={T.why}>
              <MatchWhy items={items} />
            </Panel>
          )}
          <Panel title={T.grade}>
            <p className="text-sm">
              <b>{grade ?? "Не определён"}</b>
              {c.grade_info.confidence != null && <span className="text-muted"> · уверенность {Math.round(c.grade_info.confidence * 100)}%</span>}
            </p>
            <ul className="flex flex-col gap-1 text-13">
              {c.grade_info.breakdown.map((b) => (
                <li key={b.signal} className="flex justify-between gap-3">
                  <span>{b.label}</span>
                  <span className="font-mono">{points(b.points)}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title={T.next}>
            <p className="text-12 text-muted">{T.contacts}</p>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

/** Карточка кандидата для работодателя (экран B, тёмная): анонимный DTO, пишет просмотр. */
export default function CandidateView() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const vacancyId = params.get("vacancy");
  const source = (["search", "match", "similar", "direct"] as const).find((s) => s === params.get("source")) ?? "direct";
  const q = useCandidateCardCandidatesPseudoIdCardGet(id, { vacancy_id: vacancyId ?? undefined, source }, { query: { retry: false } });
  const back = vacancyId ? `/employer/vacancies/${vacancyId}/shortlist` : "/employer";
  return (
    <ThemeScope dark className="min-h-[calc(100dvh-4rem)]">
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-4 md:p-6">
        <Link to={back} className="text-sm font-semibold text-brand-fg hover:underline">
          ← {T.back}
        </Link>
        {q.isPending && (
          <p role="status" className="text-muted">
            {T.loading}
          </p>
        )}
        {q.isError && <ErrorNote>{T.notFound}</ErrorNote>}
        {q.data?.status === 200 && <Body c={q.data.data} vacancyId={vacancyId} />}
      </main>
    </ThemeScope>
  );
}
