import { PAGE as PAGE_LAYOUT } from "@/shared/lib/page";
import { Gloss } from "@/shared/Gloss";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Button,
  buttonVariants,
  EmptyState,
  ErrorState,
  FilterChip,
  formatRub,
  H1,
  H2,
  Num,
  RankedCandidateCard,
  Select,
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
import { OfferDialog } from "@/features/offers/OfferDialog";
import { splitConfirmed, stackOptions, toRankedCard } from "./category-model";
import {
  applyFilters,
  type CandidateSort,
  type CategoryFilters,
  EMPTY_CATEGORY_FILTERS,
  gradeTitle,
  professionTitle,
  sortCards,
} from "./need-model";
import { CAT_TEXT as T, SUB_TEXT } from "./text";

const PAGE = 20;
const SORTS: [CandidateSort, string][] = [
  ["rank", T.sortRank],
  ["match", T.sortMatch],
  ["strength", T.sortStrength],
];

interface RowProps {
  c: CandidateCard;
  profession: string;
  primary: boolean;
  shortlisted: boolean;
  canShortlist: boolean;
  onToggleShortlist: () => void;
  onInterest: () => void;
  onDismiss: () => void;
  onOpen: () => void;
}

function Row({ c, profession, primary, shortlisted, canShortlist, onToggleShortlist, onInterest, onDismiss, onOpen }: RowProps) {
  return (
    <li>
      <RankedCandidateCard
        c={toRankedCard(c, profession)}
        onOpen={onOpen}
        actions={
          <>
            <Button variant={primary ? "default" : "outline"} className="h-10 md:h-9" onClick={onInterest}>
              {T.interest}
            </Button>
            {canShortlist && (
              <Button variant="outline" className="h-10 md:h-9" aria-pressed={shortlisted} onClick={onToggleShortlist}>
                {shortlisted ? `✓ ${T.shortlisted}` : T.shortlist}
              </Button>
            )}
            <Button variant="ghost" size="sm" className="h-9 md:h-8" onClick={onDismiss}>
              {T.dismiss}
            </Button>
          </>
        }
      />
    </li>
  );
}

function Skeletons() {
  return (
    <div className="grid gap-4" aria-hidden data-testid="category-loading">
      {[0, 1, 2].map((i) => (
        <div key={i} className="grid gap-2.5 rounded-xl border border-hairline bg-card p-4">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[70%]" />
        </div>
      ))}
    </div>
  );
}

/** Кандидаты категории: ранг, «заявлено vs подтверждено», шорт-лист, приглашение (макет N2). */
export default function CategoryCandidates() {
  const { profession = "", grade = "" } = useParams();
  const [params] = useSearchParams();
  const needId = params.get("need_id");
  const [interestFor, setInterestFor] = useState<CandidateCard | null>(null);
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
          need_id: needId ?? undefined,
          session_id: next ? session.current : undefined,
          cursor: next ?? undefined,
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

  // Реакции уходят в POST /recs/feedback; ответ несёт чипсы «Учли: …». Сбой не мешает работе.
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
  const groups = useMemo(() => splitConfirmed(visible, profession), [visible, profession]);
  const stacks = useMemo(() => stackOptions(items), [items]);

  const set = <K extends keyof CategoryFilters>(k: K, v: CategoryFilters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const cat = catList?.find((x) => x.profession === profession && x.grade === grade);
  const back = needId ? `/employer?need=${encodeURIComponent(needId)}&cat=${encodeURIComponent(`${profession}:${grade}`)}` : "/employer";

  if (failed === "invalid") {
    return (
      <div className={PAGE_LAYOUT.normal}>
        <EmptyState
          title={T.invalid}
          action={
            <Link to="/employer" className={buttonVariants({ variant: "outline" })}>
              {T.back}
            </Link>
          }
        />
      </div>
    );
  }

  const first = loading && items.length === 0 && !failed;
  const stat = (value: string, label: string) => (
    <span>
      <Num className="text-lg">{value}</Num> <span className="font-mono text-11 font-medium text-muted">{label}</span>
    </span>
  );
  const row = (c: CandidateCard, primary: boolean) => (
    <Row
      key={c.pseudo_id}
      c={c}
      profession={profession}
      primary={primary}
      shortlisted={shortlist.has(c.pseudo_id)}
      canShortlist={!!needId}
      onToggleShortlist={() => toggleShortlist(c.pseudo_id)}
      onInterest={() => setInterestFor(c)}
      onDismiss={() => {
        react(c.pseudo_id, "dismiss");
        setDismissed((x) => new Set(x).add(c.pseudo_id));
      }}
      onOpen={() => {
        react(c.pseudo_id, "open");
        navigate(`/employer/candidates/${c.pseudo_id}?source=match${needId ? `&need_id=${encodeURIComponent(needId)}` : ""}`);
      }}
    />
  );

  return (
    <div className={PAGE_LAYOUT.normal}>
      <header className="flex flex-col gap-2">
        <nav aria-label="Навигация">
          <Link to={back} className="text-13 font-semibold text-brand-fg hover:underline">
            ← {T.back}
          </Link>
        </nav>
        <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
          <H1 className="text-[22px] md:text-[26px]">
            <Gloss k="category">{title}</Gloss>
          </H1>
          {!first && !failed && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1" data-testid="category-stats">
              {stat(String(total ?? cat?.candidates ?? 0), T.people)}
              {cat?.median_salary ? stat(formatRub(cat.median_salary), T.median) : null}
              {cat?.fsp_share !== null && cat?.fsp_share !== undefined ? stat(`${Math.round(cat.fsp_share * 100)} %`, T.withFsp) : null}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-14">
          <Link
            to={`/employer/subscriptions?profession=${encodeURIComponent(profession)}&grade=${encodeURIComponent(grade)}`}
            className="font-semibold text-brand-fg hover:underline"
          >
            {SUB_TEXT.fromCategory}
          </Link>
          {needId && shortlist.size > 0 && <span className="font-mono text-13 font-semibold text-brand-fg">{T.shortlistCount(shortlist.size)}</span>}
        </div>
      </header>

      {first && <Skeletons />}
      {failed === "load" && <ErrorState title={T.failed} onRetry={() => void load(null)} />}

      {!first && !failed && items.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label={T.filters}>
          {stacks.length > 0 && (
            <Select
              aria-label={T.stack}
              value={filters.skill ?? ""}
              onChange={(v) => set("skill", v || null)}
              options={[{ value: "", label: T.stackAny }, ...stacks.map((n) => ({ value: n, label: n }))]}
              className="min-h-9 w-44 py-0.5 font-mono text-12"
            />
          )}
          <FilterChip pressed={filters.fspOnly} onToggle={() => set("fspOnly", !filters.fspOnly)}>
            {T.fspOnly}
          </FilterChip>
          <FilterChip pressed={filters.remoteOnly} onToggle={() => set("remoteOnly", !filters.remoteOnly)}>
            {T.remote}
          </FilterChip>
          <FilterChip pressed={filters.confirmedOnly} onToggle={() => set("confirmedOnly", !filters.confirmedOnly)}>
            {T.confirmedOnly}
          </FilterChip>
          <Select
            aria-label={T.sort}
            value={sort}
            onChange={(v) => v && setSort(v as CandidateSort)}
            options={SORTS.map(([k, label]) => ({ value: k, label }))}
            className="ml-auto min-h-9 w-52 py-0.5 font-mono text-12"
          />
        </div>
      )}

      {chips.length > 0 && (
        <ul aria-label={T.tuned} className="m-0 flex list-none flex-wrap items-center gap-2 p-0">
          {chips.map((c) => (
            <li key={c.feature} className="flex items-center gap-1 rounded-sm border border-tint-200 bg-tint-50 py-0.5 pr-1 pl-2.5 font-mono text-12 text-chip-fg">
              <span>
                {T.tuned}: {c.text}
              </span>
              <button type="button" aria-label={T.tunedReset} onClick={resetChips} className="flex size-8 items-center justify-center rounded-sm text-muted hover:bg-tint-100">
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

      {!loading && !failed && total === 0 && <EmptyState title={T.empty} />}
      {!failed && total !== 0 && items.length > 0 && visible.length === 0 && (
        <EmptyState
          title={T.emptyFiltered}
          action={
            <Button size="lg" onClick={() => setFilters(EMPTY_CATEGORY_FILTERS)}>
              {T.reset}
            </Button>
          }
        />
      )}
      {visible.length > 0 && (
        <>
          {groups.confirmed.length > 0 && (
            <ol aria-label={T.list} className="m-0 grid list-none gap-4 p-0">
              {groups.confirmed.map((c, i) => row(c, i === 0))}
            </ol>
          )}
          {groups.unconfirmed.length > 0 && (
            <section aria-label={T.unconfirmed} className="grid gap-4">
              <div className="mt-1 flex items-center justify-between gap-2">
                <Gloss k="claimed"><H2>{T.unconfirmed}</H2></Gloss>
                <Num className="text-12 text-muted">{groups.unconfirmed.length}</Num>
              </div>
              <ol aria-label={`${T.unconfirmed}: ${T.list}`} className="m-0 grid list-none gap-4 p-0">
                {groups.unconfirmed.map((c) => row(c, false))}
              </ol>
            </section>
          )}
        </>
      )}
      {total !== null && items.length > 0 && <p className="m-0 text-12 text-muted">{T.shown(visible.length, total)}</p>}
      {cursor && (
        <Button variant="outline" onClick={() => void load(cursor)} loading={loading} className="justify-self-center">
          {T.more}
        </Button>
      )}
      {interestFor && (
        <OfferDialog
          open
          stay
          mode="interest"
          onOpenChange={(v) => !v && setInterestFor(null)}
          candidate={{ pseudoId: interestFor.pseudo_id, pseudonym: interestFor.pseudonym, salaryMin: interestFor.salary_min ?? null }}
        />
      )}
    </div>
  );
}
