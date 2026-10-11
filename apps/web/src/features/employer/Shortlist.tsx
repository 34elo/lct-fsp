import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  AcceptanceMeter,
  Button,
  ChevronDown,
  ConstellationAvatar,
  EmptyState,
  ErrorState,
  FspProtocol,
  GradeBadge,
  MatchRing,
  MatchWhy,
  SectionLabel,
  SkillChip,
  Skeleton,
  cn,
  formatRubRange,
  pseudonymLabel,
  type AcceptanceLevel,
} from "@fsp/ui";

import { useRecordFeedbackRecsFeedbackPost } from "@/api/endpoints/recommendations/recommendations";
import { useSearchCandidatesSearchCandidatesPost } from "@/api/endpoints/search/search";
import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import type { CandidateCard, SearchRequestSort } from "@/api/model";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { EMPTY_FORM, gradeRange, toCardData, toFilters } from "./search-model";
import { FORMAT_LABEL, SHORTLIST_TEXT as T } from "./text";

/** Сколько первых строк подборки открыты с обоснованием. */
export const OPEN_TOP = 5;

const LEVELS: AcceptanceLevel[] = ["low", "medium", "high"];
export const acceptanceLevel = (v?: string | null): AcceptanceLevel | null => (LEVELS.includes(v as AcceptanceLevel) ? (v as AcceptanceLevel) : null);

interface RowProps {
  c: CandidateCard;
  rank: number;
  open: boolean;
  onToggle: () => void;
  onOffer: () => void;
  onOpen: () => void;
}

/** Строка подборки: кандидат, совпадение, вероятность принятия, навыки, ФСП, ожидания; под ней обоснование. */
function Row({ c, rank, open, onToggle, onOffer, onOpen }: RowProps) {
  const d = toCardData(c);
  const pseudo = pseudonymLabel(d.role, d.number);
  const level = acceptanceLevel(c.match?.interest);
  const why = d.why ?? [];
  const plus = why.filter((w) => w.kind === "ok");
  const care = why.filter((w) => w.kind !== "ok");
  const panelId = `why-${c.pseudo_id}`;
  return (
    <li>
      <article aria-label={pseudo} className="grid gap-3 border-b border-hairline p-4 last:border-b-0">
        <div className="grid items-center gap-3 md:grid-cols-[28px_minmax(0,1.1fr)_auto_minmax(0,1.4fr)_auto]">
          <span className="hidden font-mono text-16 font-semibold text-brand-fg md:block" aria-label={`Место ${rank}`}>
            {rank}
          </span>
          <button type="button" onClick={onOpen} className="flex min-w-0 items-center gap-3 text-left" aria-label={`Открыть профиль ${pseudo}`}>
            <ConstellationAvatar seed={pseudo} />
            <span className="grid min-w-0 gap-1">
              <span className="font-mono text-15 font-semibold">
                <span className="mr-2 text-brand-fg md:hidden">{rank}.</span>
                {pseudo}
              </span>
              <GradeBadge grade={d.grade} stack={d.stack} preliminary={d.gradePreliminary} className="w-fit" />
            </span>
          </button>
          <div className="flex items-center gap-4">
            <MatchRing value={d.match} size={52} />
          </div>
          <div className="grid min-w-0 gap-2">
            <ul className="flex flex-wrap gap-1.5" aria-label="Ключевые навыки">
              {d.skills.slice(0, 3).map((s) => (
                <li key={s.name}>
                  <SkillChip name={s.name} level={s.level} variant={s.variant} />
                </li>
              ))}
            </ul>
            {d.fsp && d.fsp.length > 0 ? <FspProtocol results={d.fsp.slice(0, 1)} /> : <p className="text-12 text-muted">{T.noFsp}</p>}
          </div>
          <div className="flex items-center gap-2 md:justify-end">
            {d.expectations?.[0] ? <span className="mr-auto font-mono text-13 font-semibold md:mr-3">{d.expectations[0]}</span> : null}
            <Button size="sm" onClick={onOffer}>
              {T.offer}
            </Button>
            <Button
              size="sm"
              variant="outline"
              aria-expanded={open}
              aria-controls={panelId}
              aria-label={open ? T.collapse(pseudo) : T.expand(pseudo)}
              onClick={onToggle}
            >
              <ChevronDown aria-hidden className={cn("size-4 transition-transform", open && "rotate-180")} />
            </Button>
          </div>
        </div>
        {level ? <AcceptanceMeter level={level} /> : null}
        {open && (
          <div id={panelId} className="grid gap-4 rounded-lg border border-tint-200 bg-tint-50 p-4 md:grid-cols-2">
            <div className="grid content-start gap-2">
              <SectionLabel>{T.why}</SectionLabel>
              {plus.length > 0 ? <MatchWhy items={plus} /> : <p className="text-13 text-muted">{T.noWhy}</p>}
            </div>
            <div className="grid content-start gap-2">
              <SectionLabel>{T.care}</SectionLabel>
              {care.length > 0 ? <MatchWhy items={care} /> : <p className="text-13 text-muted">{T.noCare}</p>}
              {level ? <p className="text-13 font-semibold text-brand-fg">{T.interest(level)}</p> : null}
            </div>
          </div>
        )}
      </article>
    </li>
  );
}

/** Подборка по вакансии: ранжированный список, обоснование открыто у первых пяти. */
export default function Shortlist() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const vacancies = useListVacanciesVacanciesGet();
  const search = useSearchCandidatesSearchCandidatesPost();
  const feedback = useRecordFeedbackRecsFeedbackPost();
  const [sort, setSort] = useState<SearchRequestSort>("mutual");
  const [items, setItems] = useState<CandidateCard[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const session = useRef<string | null>(null);
  const seq = useRef(0);

  const list = useMemo(() => (vacancies.data?.status === 200 ? vacancies.data.data : []), [vacancies.data]);
  const vacancy = list.find((v) => v.id === id) ?? null;
  const ready = vacancy !== null || vacancies.isError;

  const run = useCallback(
    (next: string | null) => {
      const n = ++seq.current;
      setFailed(false);
      const form = vacancy ? { ...EMPTY_FORM, roles: [vacancy.role], grades: gradeRange(vacancy.grade_min, vacancy.grade_max) } : EMPTY_FORM;
      search.mutate(
        { data: { filters: toFilters(form), sort, cursor: next, limit: 20, vacancy_id: id, session_id: next ? session.current : null } },
        {
          onSuccess: (r) => {
            if (n !== seq.current || r.status !== 200) return;
            session.current = r.data.session_id;
            setItems((old) => (next ? [...old, ...r.data.items] : r.data.items));
            setCursor(r.data.next_cursor);
            setTotal(r.data.total);
          },
          onError: () => n === seq.current && setFailed(true),
        },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [vacancy?.id, sort, id],
  );
  useEffect(() => {
    if (ready) run(null);
  }, [ready, sort, id]); // eslint-disable-line react-hooks/exhaustive-deps

  const react = (c: CandidateCard, event: "open" | "shortlist") => {
    if (session.current) feedback.mutate({ data: { session_id: session.current, candidate_pseudo_id: c.pseudo_id, event } });
  };
  // Переключатель «по интересу / по совпадению» нужен, только если API отдаёт интерес кандидата.
  const withInterest = useMemo(() => items.some((c) => c.match?.interest), [items]);
  const pending = search.isPending;
  const fspCount = items.filter((c) => c.fsp_highlights.length > 0).length;

  if (vacancies.isPending) return <Skeleton aria-hidden className="m-6 h-64 rounded-xl" />;
  if (vacancies.isSuccess && !vacancy) {
    return (
      <div className="p-6">
        <EmptyState
          title={T.notFound}
          action={
            <Link to="/employer/vacancies" className="font-semibold text-brand-fg hover:underline">
              {T.toVacancies}
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="grid gap-6 px-4 py-6 md:px-6 lg:px-10 lg:py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="grid gap-1">
          <SectionLabel>{T.kicker}</SectionLabel>
          <h1 className="font-mono text-24 font-semibold">{vacancy?.title ?? T.title}</h1>
          {vacancy && (
            <p className="font-mono text-13 text-muted">
              {formatRubRange(vacancy.salary_from, vacancy.salary_to)} · {roleLabel(vacancy.role)} · {GRADE_LABEL[vacancy.grade_min]}–
              {GRADE_LABEL[vacancy.grade_max]} · {vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}
              {total !== null ? ` · ${T.count(total, fspCount)}` : ""}
            </p>
          )}
        </div>
        {withInterest && (
          <div role="group" aria-label={T.sort} className="inline-flex overflow-hidden rounded-lg border border-hairline">
            {(
              [
                ["mutual", T.byInterest],
                ["match", T.byMatch],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                type="button"
                aria-pressed={sort === k}
                onClick={() => setSort(k)}
                className={cn("h-10 px-3 text-13 font-semibold", sort === k ? "bg-brand text-on-brand" : "bg-card text-ink hover:bg-tint-50")}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </header>

      {withInterest && sort === "mutual" && <p className="rounded-lg border border-tint-200 bg-tint-50 px-4 py-3 text-13">{T.mutualHint}</p>}

      {failed && <ErrorState title={T.failed} onRetry={() => run(null)} />}
      {pending && items.length === 0 && !failed && (
        <div className="grid gap-3" aria-hidden>
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-28 rounded-xl" />
        </div>
      )}
      {total === 0 && !pending && !failed && <EmptyState title={T.empty} description={T.emptyHint} />}

      {items.length > 0 && (
        <ol aria-label={T.list} className="overflow-hidden rounded-xl border border-hairline bg-card shadow-xs">
          {items.map((c, i) => (
            <Row
              key={c.pseudo_id}
              c={c}
              rank={i + 1}
              open={toggled[c.pseudo_id] ?? i < OPEN_TOP}
              onToggle={() => setToggled((t) => ({ ...t, [c.pseudo_id]: !(t[c.pseudo_id] ?? i < OPEN_TOP) }))}
              onOpen={() => {
                react(c, "open");
                navigate(`/employer/candidates/${c.pseudo_id}?vacancy=${id}&source=match`);
              }}
              onOffer={() => {
                react(c, "shortlist");
                navigate(`/employer/offers/new?candidate=${c.pseudo_id}&vacancy=${id}`);
              }}
            />
          ))}
        </ol>
      )}
      {items.length > 0 && <p className="text-12 text-muted">{T.footnote(OPEN_TOP)}</p>}
      {cursor && (
        <Button variant="outline" onClick={() => run(cursor)} loading={pending} className="justify-self-center">
          {T.more}
        </Button>
      )}
    </div>
  );
}
