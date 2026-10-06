import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Button,
  Checkbox,
  cn,
  ConstellationAvatar,
  EmptyState,
  ErrorState,
  FspProtocol,
  GradeBadge,
  MatchRing,
  MatchWhy,
  pseudonymLabel,
  SectionLabel,
  SkillChip,
  Skeleton,
} from "@fsp/ui";

import {
  categoryCandidatesCategoriesProfessionGradeCandidatesGet,
  useNeedCategoriesNeedsNeedIdCategoriesGet,
  useShortlistAddNeedsNeedIdShortlistPseudoIdPost,
  useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete,
} from "@/api/endpoints/needs/needs";
import {
  useRecordFeedbackRecsFeedbackPost,
  useResetSessionTuningRecsSessionsSessionIdDelete,
} from "@/api/endpoints/recommendations/recommendations";
import type { CandidateCard, Chip } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { toCardData } from "@/features/employer/search-model";
import {
  applyFilters,
  claimedVsConfirmed,
  type CandidateSort,
  type CategoryFilters,
  EMPTY_CATEGORY_FILTERS,
  fixed2,
  gradeTitle,
  isDefaultFilters,
  professionTitle,
  sortCards,
} from "./need-model";
import { CAT_TEXT as T } from "./text";

const PAGE = 20;
const STATUS_TEXT = { match: T.stMatch, below: T.stBelow, above: T.stAbove, none: T.stNone } as const;
const STATUS_MARK = { match: "✓", below: "⚠", above: "↑", none: "—" } as const;
const SORTS: [CandidateSort, string][] = [
  ["rank", T.sortRank],
  ["match", T.sortMatch],
  ["strength", T.sortStrength],
];

interface RowProps {
  c: CandidateCard;
  place: number;
  profession: string;
  shortlisted: boolean;
  canShortlist: boolean;
  onToggleShortlist: () => void;
  onInvite: () => void;
  onDismiss: () => void;
  onOpen: () => void;
}

function Row({ c, place, profession, shortlisted, canShortlist, onToggleShortlist, onInvite, onDismiss, onOpen }: RowProps) {
  const d = toCardData(c);
  const pseudo = pseudonymLabel(d.role, d.number);
  const cv = claimedVsConfirmed(c, profession);
  const rank = c.strength?.rank != null ? fixed2(c.strength.rank) : null;
  const why = d.why ?? [];
  const top = c.strength?.top ?? [];
  return (
    <li>
      <article aria-label={pseudo} className="grid gap-4 rounded-xl border border-hairline bg-card p-4 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <button type="button" onClick={onOpen} aria-label={`Открыть профиль ${pseudo}`} className="flex min-w-0 items-center gap-3 text-left">
            <ConstellationAvatar seed={pseudo} />
            <span className="grid min-w-0 gap-1">
              <span className="font-mono text-15 font-semibold">{pseudo}</span>
              <span className="flex flex-wrap items-center gap-2">
                <GradeBadge grade={d.grade} preliminary={d.gradePreliminary} />
                <span className="text-12 text-muted">{T.place(place, rank)}</span>
              </span>
            </span>
          </button>
          <div className="flex items-center gap-4">
            <div className="grid justify-items-center gap-1 text-center">
              <MatchRing value={d.match} size={52} />
              <span className="text-xs text-muted">{T.match}</span>
            </div>
            <div className="grid gap-0.5 text-center">
              <span className="font-mono text-18 font-semibold">{c.strength ? fixed2(c.strength.value) : "—"}</span>
              <span className="text-xs text-muted">{T.strength}</span>
            </div>
          </div>
        </div>

        <ul className="flex flex-wrap gap-1.5" aria-label="Ключевые навыки">
          {d.skills.slice(0, 5).map((s) => (
            <li key={s.name}>
              <SkillChip name={s.name} level={s.level} variant={s.variant} />
            </li>
          ))}
        </ul>

        <section aria-label={T.claimedVs} className="grid gap-2 rounded-lg border border-tint-200 bg-tint-50 p-3">
          <SectionLabel>{T.claimedVs}</SectionLabel>
          <div className="flex flex-wrap items-center gap-3 font-mono text-13">
            <span>
              <span className="text-muted">{T.claimed}: </span>
              <b>{cv.claimed ? gradeTitle(cv.claimed) : T.notSpecified}</b>
            </span>
            <span aria-hidden>→</span>
            <span>
              <span className="text-muted">{T.confirmed}: </span>
              <b>{cv.confirmed ? gradeTitle(cv.confirmed) : T.noTest}</b>
            </span>
            <span
              className={cn(
                "rounded-md px-2 py-0.5 text-12 font-semibold",
                cv.status === "below" ? "bg-warning-bg text-warning-fg" : cv.status === "none" ? "bg-card text-muted" : "bg-card text-brand-fg",
              )}
            >
              {STATUS_MARK[cv.status]} {STATUS_TEXT[cv.status]}
            </span>
          </div>
          <p className="text-12 text-muted">{cv.confirmed ? T.noteTest : T.noteNone}</p>
        </section>

        {why.length > 0 || top.length > 0 ? (
          <div className="grid gap-3 md:grid-cols-2">
            {why.length > 0 && <MatchWhy items={why} />}
            {top.length > 0 && (
              <ul className="grid gap-1 text-13" aria-label={T.strength}>
                {top.map((p) => (
                  <li key={p.code} className="flex justify-between gap-3">
                    <span>{p.text}</span>
                    <span className="font-mono text-muted">{fixed2(p.value)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <p className="text-13 text-muted">{T.noWhy}</p>
        )}
        {d.fsp && d.fsp.length > 0 ? <FspProtocol results={d.fsp.slice(0, 1)} /> : <p className="text-12 text-muted">{T.noFsp}</p>}

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={onInvite}>
            {T.invite}
          </Button>
          {canShortlist && (
            <Button size="sm" variant="outline" aria-pressed={shortlisted} onClick={onToggleShortlist}>
              {shortlisted ? `✓ ${T.shortlisted}` : T.shortlist}
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            {T.dismiss}
          </Button>
          {d.expectations?.[0] && <span className="ml-auto font-mono text-13 font-semibold">{d.expectations[0]}</span>}
        </div>
      </article>
    </li>
  );
}

/** Кандидаты категории: ранг, «заявлено vs подтверждено», шорт-лист, приглашение (макет N2). */
export default function CategoryCandidates() {
  const { profession = "", grade = "" } = useParams();
  const [params] = useSearchParams();
  const needId = params.get("need_id");
  const navigate = useNavigate();

  const [items, setItems] = useState<CandidateCard[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState<"load" | "invalid" | null>(null);
  const [sort, setSort] = useState<CandidateSort>("rank");
  const [filters, setFilters] = useState<CategoryFilters>(EMPTY_CATEGORY_FILTERS);
  const [shortlist, setShortlist] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [shortlistError, setShortlistError] = useState(false);
  const [chips, setChips] = useState<Chip[]>([]);
  const seq = useRef(0);
  const session = useRef<string | null>(null);

  const cats = useNeedCategoriesNeedsNeedIdCategoriesGet(needId ?? "", { query: { enabled: !!needId } });
  const catList = cats.data?.status === 200 ? cats.data.data.categories : undefined;
  const title = `${professionTitle(profession, catList)} · ${gradeTitle(grade)}`;

  const add = useShortlistAddNeedsNeedIdShortlistPseudoIdPost();
  const feedback = useRecordFeedbackRecsFeedbackPost();
  const resetTuning = useResetSessionTuningRecsSessionsSessionIdDelete();
  const remove = useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete();

  const load = useCallback(
    async (next: string | null) => {
      const n = ++seq.current;
      setLoading(true);
      setFailed(null);
      try {
        const r = await categoryCandidatesCategoriesProfessionGradeCandidatesGet(profession, grade, {
          need_id: needId,
          session_id: next ? session.current : null,
          cursor: next,
          limit: PAGE,
        });
        if (n !== seq.current || r.status !== 200) return;
        session.current = r.data.session_id;
        if (!next) setChips([]);
        setItems((old) => (next ? [...old, ...r.data.items] : r.data.items));
        setCursor(r.data.next_cursor);
        setTotal(r.data.total);
        setShortlist((old) => {
          const s = new Set(next ? old : []);
          for (const c of r.data.items) if (c.is_shortlisted) s.add(c.pseudo_id);
          return s;
        });
      } catch (e) {
        if (n === seq.current) setFailed(e instanceof ApiError && e.code === "invalid_category" ? "invalid" : "load");
      } finally {
        if (n === seq.current) setLoading(false);
      }
    },
    [profession, grade, needId],
  );
  useEffect(() => {
    void load(null);
  }, [load]);

  // Реакции уходят в POST /recs/feedback; ответ несёт чипсы «Учли: …» (matching.md §7). Сбой не мешает работе.
  const react = (id: string, event: "open" | "shortlist" | "dismiss") => {
    if (!session.current) return;
    feedback.mutate(
      { data: { session_id: session.current, candidate_pseudo_id: id, event } },
      { onSuccess: (r) => r.status === 200 && setChips(r.data.tuning.chips) },
    );
  };
  const resetChips = () => {
    if (session.current) resetTuning.mutate({ sessionId: session.current });
    setChips([]);
  };

  const toggleShortlist = (id: string) => {
    if (!needId) return;
    const on = !shortlist.has(id);
    if (on) react(id, "shortlist");
    setShortlistError(false);
    setShortlist((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
    const revert = () => {
      setShortlistError(true);
      setShortlist((s) => {
        const n = new Set(s);
        if (on) n.delete(id);
        else n.add(id);
        return n;
      });
    };
    (on ? add : remove).mutate({ needId, pseudoId: id }, { onError: revert });
  };

  const visible = useMemo(() => {
    const base = items.filter((c) => !dismissed.has(c.pseudo_id));
    return sortCards(applyFilters(base, filters, profession, shortlist), sort);
  }, [items, dismissed, filters, profession, shortlist, sort]);

  const set = <K extends keyof CategoryFilters>(k: K, v: CategoryFilters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const check = (k: "confirmedOnly" | "fspOnly" | "remoteOnly", label: string) => (
    <label className="flex min-h-11 items-center gap-2 text-13">
      <Checkbox checked={filters[k]} onCheckedChange={(v) => set(k, v === true)} aria-label={label} />
      {label}
    </label>
  );

  if (failed === "invalid") {
    return (
      <div className="p-6">
        <EmptyState
          title={T.invalid}
          action={
            <Link to="/employer/needs/new" className="font-semibold text-brand-fg hover:underline">
              {T.back}
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="grid gap-6 px-4 py-6 md:px-6 lg:px-10 lg:py-8">
      <header className="grid gap-2">
        <nav aria-label="Навигация" className="text-13 text-muted">
          <Link to={needId ? `/employer/needs/${needId}` : "/employer/needs/new"} className="font-semibold text-brand-fg hover:underline">
            {T.kicker}
          </Link>{" "}
          / {title}
        </nav>
        <h1 className="font-mono text-24 font-semibold">{title}</h1>
        {total !== null && <p className="text-14 text-muted">{T.lead(total)}</p>}
        {needId && shortlist.size > 0 && <p className="font-mono text-13 font-semibold text-brand-fg">{T.shortlistCount(shortlist.size)}</p>}
      </header>

      <div className="grid items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside aria-label={T.filters} className="grid gap-3 rounded-xl border border-hairline bg-card p-4">
          <SectionLabel>{T.sort}</SectionLabel>
          <div role="group" aria-label={T.sort} className="inline-flex overflow-hidden rounded-lg border border-hairline">
            {SORTS.map(([k, label]) => (
              <button
                key={k}
                type="button"
                aria-pressed={sort === k}
                onClick={() => setSort(k)}
                className={cn("h-11 flex-1 px-2 text-12 font-semibold sm:h-10", sort === k ? "bg-brand text-on-brand" : "bg-card text-ink hover:bg-tint-50")}
              >
                {label}
              </button>
            ))}
          </div>
          <SectionLabel>{T.filters}</SectionLabel>
          <label className="grid gap-1 text-13">
            {T.minStrength}
            <select
              value={filters.minStrength}
              onChange={(e) => set("minStrength", Number(e.target.value))}
              className="h-11 rounded-lg border border-hairline bg-card px-3 text-14"
            >
              <option value={0}>Любая</option>
              <option value={0.3}>от 0,30</option>
              <option value={0.5}>от 0,50</option>
              <option value={0.7}>от 0,70</option>
            </select>
          </label>
          {check("confirmedOnly", T.confirmedOnly)}
          {check("fspOnly", T.fspOnly)}
          {check("remoteOnly", T.remote)}
          <label className="grid gap-1 text-13">
            {T.budget}
            <input
              inputMode="numeric"
              value={filters.budgetMax ?? ""}
              onChange={(e) => {
                const n = Number(e.target.value.replace(/\D/g, ""));
                set("budgetMax", n > 0 ? n : null);
              }}
              placeholder="220000"
              className="h-11 rounded-lg border border-hairline bg-card px-3 font-mono text-14"
            />
          </label>
          <Button variant="ghost" size="sm" disabled={isDefaultFilters(filters)} onClick={() => setFilters(EMPTY_CATEGORY_FILTERS)}>
            {T.reset}
          </Button>
          <p className="text-12 text-muted">{T.filterNote}</p>
        </aside>

        <section className="grid min-w-0 gap-4">
          {failed === "load" && <ErrorState title={T.failed} onRetry={() => void load(null)} />}
          {chips.length > 0 && (
            <ul aria-label={T.tuned} className="flex flex-wrap items-center gap-2">
              {chips.map((c) => (
                <li key={c.feature} className="flex items-center gap-1 rounded-full border border-tint-200 bg-tint-50 py-1 pl-3 pr-1 text-13">
                  <span>
                    {T.tuned}: {c.text}
                  </span>
                  <button
                    type="button"
                    aria-label={T.tunedReset}
                    onClick={resetChips}
                    className="flex size-8 items-center justify-center rounded-full text-muted hover:bg-tint-100"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          {shortlistError && (
            <p role="alert" className="text-13 text-error">
              {T.shortlistFailed}
            </p>
          )}
          {loading && items.length === 0 && !failed && (
            <div className="grid gap-3" aria-hidden>
              <Skeleton className="h-56 rounded-xl" />
              <Skeleton className="h-56 rounded-xl" />
            </div>
          )}
          {!loading && !failed && total === 0 && <EmptyState title={T.empty} />}
          {!failed && total !== 0 && items.length > 0 && visible.length === 0 && <EmptyState title={T.emptyFiltered} description={T.emptyFilteredHint} />}
          {visible.length > 0 && (
            <ol aria-label={T.list} className="grid gap-4">
              {visible.map((c, i) => (
                <Row
                  key={c.pseudo_id}
                  c={c}
                  place={i + 1}
                  profession={profession}
                  shortlisted={shortlist.has(c.pseudo_id)}
                  canShortlist={!!needId}
                  onToggleShortlist={() => toggleShortlist(c.pseudo_id)}
                  onInvite={() => navigate(`/employer/offers/new?candidate=${c.pseudo_id}`)}
                  onDismiss={() => {
                    react(c.pseudo_id, "dismiss");
                    setDismissed((s) => new Set(s).add(c.pseudo_id));
                  }}
                  onOpen={() => {
                    react(c.pseudo_id, "open");
                    navigate(`/employer/candidates/${c.pseudo_id}?source=match`);
                  }}
                />
              ))}
            </ol>
          )}
          {total !== null && items.length > 0 && <p className="text-12 text-muted">{T.shown(visible.length, total)}</p>}
          {cursor && (
            <Button variant="outline" onClick={() => void load(cursor)} loading={loading} className="justify-self-center">
              {T.more}
            </Button>
          )}
        </section>
      </div>
    </div>
  );
}
