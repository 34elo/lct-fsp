import { Link, useParams, useSearchParams } from "react-router-dom";

import { useCandidateCardCandidatesPseudoIdCardGet } from "@/api/endpoints/search/search";
import type { CandidateCardFull, SkillWithTrust } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { dots, GRADE_LABEL, points, roleLabel } from "@/features/profile/text";
import { ConstellationAvatar, MatchRing, SkillChip, TrustDots, type TrustKind } from "@/shared/brand";
import { cn } from "@/shared/lib/cn";
import { FORMAT_LABEL, percent, rub, SEARCH_STATUS_LABEL, SOURCE_SHORT, splitExplanation } from "./text";

function Section({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={title} className={cn("flex flex-col gap-3 rounded-xl border border-hairline bg-card p-5", className)}>
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

function Skill({ s }: { s: SkillWithTrust }) {
  const kind = kindOf(s);
  return (
    <li className="flex flex-col gap-1.5 border-t border-hairline pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <SkillChip name={s.skill.name} variant={kind} />
        <TrustDots level={dots(s.level)} kind={kind} />
        <span className="text-xs text-muted">{s.sources.map((x) => SOURCE_SHORT[x] ?? x).join(", ")}</span>
      </div>
      {s.claimed_only && <p className="text-[13px] text-muted">Только заявлено, независимого подтверждения нет.</p>}
      {s.top_evidence.length > 0 && (
        <ul className="flex flex-col gap-1 text-[13px]">
          {s.top_evidence.map((e) => (
            <li key={e.id} className="flex gap-2">
              <span aria-hidden className={e.verified ? "text-success" : "text-muted"}>{e.verified ? "✓" : "·"}</span>
              <span>
                {e.title} <span className="text-muted">({SOURCE_SHORT[e.source] ?? e.source}, {new Date(e.observed_at).getFullYear()})</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function Body({ c, vacancyId }: { c: CandidateCardFull; vacancyId: string | null }) {
  const grade = c.grade ? (GRADE_LABEL[c.grade] ?? c.grade) : null;
  const ex = c.match ? splitExplanation(c.match.explanation) : null;
  const offered = c.offers_from_you.length > 0;
  const offerHref = `/employer/offers/new?candidate=${c.pseudo_id}${vacancyId ? `&vacancy=${vacancyId}` : ""}`;
  return (
    <div className="flex flex-col gap-4">
      <section aria-label="Шапка карточки" className="flex flex-col gap-4 rounded-xl border border-hairline bg-card p-5 md:flex-row md:items-center">
        <ConstellationAvatar seed={c.avatar_seed} size={72} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h1 className="break-words font-mono text-2xl font-semibold">{c.pseudonym}</h1>
          <p className="text-sm text-muted">
            {[grade && `${grade}${c.grade_preliminary ? " (предварительно)" : ""}`, c.primary_role && roleLabel(c.primary_role), c.primary_stack.slice(0, 3).join(", ")]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className="text-[13px] text-muted">
            {[
              c.city,
              c.relocation ? "готов к релокации" : null,
              c.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", "),
              c.salary_min ? `от ${rub(c.salary_min)}` : null,
              SEARCH_STATUS_LABEL[c.search_status],
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        {c.match && <MatchRing value={percent(c.match.score)} size={72} />}
        <div className="flex flex-col gap-1">
          {/* Точка интеграции: модалку оффера делает E8-6. */}
          <Link to={offerHref} className="inline-flex h-11 items-center justify-center rounded-lg bg-brand px-4 font-semibold text-on-brand hover:bg-brand-deep">
            Отправить оффер
          </Link>
          {offered && <span className="text-xs text-muted">Оффер уже отправлялся: {c.offers_from_you.map((o) => o.status).join(", ")}</span>}
        </div>
      </section>

      {ex && (ex.pluses.length > 0 || ex.others.length > 0) && (
        <Section title="Почему подходит">
          <ul className="flex flex-col gap-1.5 text-sm">
            {ex.pluses.map((i, n) => (
              <li key={`p${n}`} className="flex gap-2"><span aria-hidden className="text-success">+</span>{i.text}</li>
            ))}
            {ex.others.map((i, n) => (
              <li key={`w${n}`} className="flex gap-2 text-muted"><span aria-hidden className="text-warning">!</span>{i.text}</li>
            ))}
          </ul>
        </Section>
      )}

      {c.fsp_highlights.length > 0 && (
        <Section title="Достижения ФСП">
          <ul className="flex flex-col gap-1 text-sm">
            {c.fsp_highlights.map((h, n) => (
              <li key={n}>
                {h.title}
                {h.place ? `, ${h.place}${h.of ? ` из ${h.of}` : ""} место` : ""} <span className="text-muted">· {h.year}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Навыки и доказательства">
        {c.skills.length === 0 ? (
          <p className="text-sm text-muted">Навыки ещё не подтверждены.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {c.skills.map((s) => (
              <Skill key={s.skill.slug} s={s} />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Грейд">
        <p className="text-sm">
          <b>{grade ?? "Не определён"}</b>
          {c.grade_info.confidence != null && <span className="text-muted"> · уверенность {Math.round(c.grade_info.confidence * 100)}%</span>}
        </p>
        <ul className="flex flex-col gap-1 text-[13px]">
          {c.grade_info.breakdown.map((b) => (
            <li key={b.signal} className="flex justify-between gap-3">
              <span>{b.label}</span>
              <span className="font-mono">{points(b.points)}</span>
            </li>
          ))}
        </ul>
      </Section>

      {c.experience.length > 0 && (
        <Section title="Опыт">
          <ul className="flex flex-col gap-1 text-sm">
            {c.experience.map((e, n) => (
              <li key={n}>
                {e.title ?? "Роль не указана"}
                {e.company ? `, ${e.company}` : ""} <span className="text-muted">· {Math.round(e.months / 12 * 10) / 10} лет</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

/** Карточка кандидата для работодателя (экран B): анонимный DTO, пишет просмотр. */
export default function CandidateView() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const vacancyId = params.get("vacancy");
  const source = (["search", "match", "similar", "direct"] as const).find((s) => s === params.get("source")) ?? "direct";
  const q = useCandidateCardCandidatesPseudoIdCardGet(id, { vacancy_id: vacancyId ?? undefined, source }, { query: { retry: false } });
  const back = vacancyId ? `/employer/vacancies/${vacancyId}/shortlist` : "/employer/search";
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <Link to={back} className="text-sm font-semibold text-brand-fg hover:underline">← К выдаче</Link>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && <ErrorNote>Кандидат не найден или скрыт.</ErrorNote>}
      {q.data?.status === 200 && <Body c={q.data.data} vacancyId={vacancyId} />}
    </main>
  );
}
