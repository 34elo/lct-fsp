import { Link } from "react-router-dom";

import type { CandidateCard } from "@/api/model";
import { dots, GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { ConstellationAvatar, MatchRing, SkillChip } from "@/shared/brand";
import { FORMAT_LABEL, percent, rub, SEARCH_STATUS_LABEL, splitExplanation } from "./text";

/** Строка-«почему подходит»: плюс или предупреждение, текст собран бэкендом из путей графа. */
function Why({ card }: { card: CandidateCard }) {
  if (!card.match) return null;
  const { pluses, others } = splitExplanation(card.match.explanation);
  if (pluses.length + others.length === 0) return null;
  return (
    <ul aria-label="Почему подходит" className="flex flex-col gap-1 text-[13px]">
      {pluses.slice(0, 3).map((i, n) => (
        <li key={`p${n}`} className="flex gap-2">
          <span aria-hidden className="text-success">+</span>
          <span>{i.text}</span>
        </li>
      ))}
      {others.slice(0, 2).map((i, n) => (
        <li key={`w${n}`} className="flex gap-2 text-muted">
          <span aria-hidden className="text-warning">!</span>
          <span>{i.text}</span>
        </li>
      ))}
    </ul>
  );
}

export function CandidateTile({ card, vacancyId }: { card: CandidateCard; vacancyId?: string | null }) {
  const q = vacancyId ? `?vacancy=${vacancyId}&source=match` : "?source=search";
  const grade = card.grade ? (GRADE_LABEL[card.grade] ?? card.grade) : null;
  const head = [grade, card.primary_role ? roleLabel(card.primary_role) : null].filter(Boolean).join(" · ");
  const offerHref = `/employer/offers/new?candidate=${card.pseudo_id}${vacancyId ? `&vacancy=${vacancyId}` : ""}`;
  return (
    <article aria-label={card.pseudonym} className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4 shadow-card">
      <div className="flex items-start gap-3">
        <ConstellationAvatar seed={card.avatar_seed} size={48} />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <Link to={`/employer/candidates/${card.pseudo_id}${q}`} className="break-words font-mono text-[17px] font-semibold hover:underline">
            {card.pseudonym}
          </Link>
          <span className="text-[13px] text-muted">
            {head || "Роль не указана"}
            {card.grade_preliminary && grade ? " (предв.)" : ""}
          </span>
          <span className="text-[13px] text-muted">
            {[
              card.city,
              card.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", "),
              card.salary_min ? `от ${rub(card.salary_min)}` : null,
              SEARCH_STATUS_LABEL[card.search_status],
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
        {card.match && <MatchRing value={percent(card.match.score)} size={56} />}
      </div>

      {card.fsp_highlights.length > 0 && (
        <p className="rounded-md bg-tint-50 px-3 py-2 text-[13px] font-medium text-brand-deep dark:text-brand-mid">
          ФСП: {card.fsp_highlights[0]!.title}
          {card.fsp_highlights[0]!.place ? `, ${card.fsp_highlights[0]!.place} место` : ""} · {card.fsp_highlights[0]!.year}
        </p>
      )}

      <div className="flex flex-wrap gap-1.5" aria-label="Навыки">
        {card.top_skills.slice(0, 6).map((s) => (
          <SkillChip
            key={s.slug}
            name={s.name}
            level={dots(s.level)}
            variant={s.sources.length === 1 && s.sources[0] === "resume" ? "claimed" : "verified"}
          />
        ))}
      </div>

      <Why card={card} />

      <div className="flex flex-wrap gap-2 pt-1">
        <Link to={`/employer/candidates/${card.pseudo_id}${q}`} className="inline-flex h-9 items-center rounded-lg border border-brand px-3 text-sm font-semibold text-brand hover:bg-tint-50">
          Открыть карточку
        </Link>
        {/* Точка интеграции: модалку оффера делает E8-6, пока ведёт на заглушку маршрута. */}
        <Link to={offerHref} className="inline-flex h-9 items-center rounded-lg bg-brand px-3 text-sm font-semibold text-on-brand hover:bg-brand-deep">
          Отправить оффер
        </Link>
      </div>
    </article>
  );
}
