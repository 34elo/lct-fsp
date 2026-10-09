import { PAGE } from "@/shared/lib/page";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  Button,
  CandidateCard as CandidateCardView,
  EmptyState,
  ErrorState,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
  Select,
  Skeleton,
  SlidersHorizontal,
  cn,
} from "@fsp/ui";

import { useRecordFeedbackRecsFeedbackPost } from "@/api/endpoints/recommendations/recommendations";
import { useSearchCandidatesSearchCandidatesPost, useSearchParseSearchParsePost } from "@/api/endpoints/search/search";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import type { CandidateCard, FilterChip, SearchRequestSort, VacancyOut } from "@/api/model";
import { OfferDialog } from "@/features/offers/OfferDialog";
import { QueryBar } from "./QueryBar";
import { chipActive, EMPTY_FORM, fromParsed, gradeRange, removeChip, toCardData, toFilters, type SearchForm } from "./search-model";
import { SearchFiltersPanel } from "./SearchFiltersPanel";
import { SEARCH_TEXT as T, SORT_LABEL } from "./text";

/** Стартовые фильтры подборки: роль и грейды вакансии. */
function vacancyForm(v: VacancyOut | null, sort: SearchRequestSort = "match"): SearchForm {
  if (!v) return { ...EMPTY_FORM, sort };
  return { ...EMPTY_FORM, roles: [v.role], grades: gradeRange(v.grade_min, v.grade_max), sort: "match" };
}

type Feedback = "open" | "shortlist" | "dismiss";

/**
 * Экран A (поиск) и E2 («текст → чипсы»); с вакансией — подборка E4. Текст разбирается в фильтры
 * (`POST /search/parse`), фильтры слева правят ту же форму, выдача пересобирается с задержкой 150 мс.
 * Реакции «В шорт-лист», «Не подходит», «Открыть профиль» уходят в `POST /recs/feedback`.
 */
export default function Search() {
  const { id: pathVacancy } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const vacancyId = pathVacancy ?? params.get("vacancy");

  const vacancies = useListVacanciesVacanciesGet();
  const taxonomy = useGetTaxonomyTaxonomyGet();
  const search = useSearchCandidatesSearchCandidatesPost();
  const parse = useSearchParseSearchParsePost();
  const feedback = useRecordFeedbackRecsFeedbackPost();

  const [form, setForm] = useState<SearchForm>(EMPTY_FORM);
  const [query, setQuery] = useState("");
  const [chips, setChips] = useState<FilterChip[] | null>(null);
  const [parseKey, setParseKey] = useState(0);
  const [parseError, setParseError] = useState<string | null>(null);
  const [items, setItems] = useState<CandidateCard[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [interestFor, setInterestFor] = useState<CandidateCard | null>(null);
  const [shortlisted, setShortlisted] = useState<Set<string>>(() => new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());
  const [sheetOpen, setSheetOpen] = useState(false);
  const session = useRef<string | null>(null);
  const seq = useRef(0);

  const myVacancies = useMemo(() => (vacancies.data?.status === 200 ? vacancies.data.data : []), [vacancies.data]);
  const vacancy = myVacancies.find((v) => v.id === vacancyId) ?? null;
  // Ответ /taxonomy в схеме без модели (unknown): сужаем до нужных полей.
  const taxSkills = useMemo(
    () => (taxonomy.data?.data as { skills?: { slug: string; name: string }[] } | undefined)?.skills ?? [],
    [taxonomy.data],
  );
  const names = useMemo(() => new Map(taxSkills.map((s) => [s.slug, s.name])), [taxSkills]);
  const skillName = useCallback((slug: string) => names.get(slug) ?? slug, [names]);

  // При выборе вакансии подставляем её роль и грейды как стартовые фильтры.
  useEffect(() => {
    if (vacancy) setForm(vacancyForm(vacancy));
  }, [vacancy?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(
    (next: string | null) => {
      const n = ++seq.current;
      setFailed(false);
      search.mutate(
        {
          data: {
            filters: toFilters(form),
            sort: form.sort,
            cursor: next,
            limit: 20,
            vacancy_id: vacancyId,
            session_id: next ? session.current : null,
          },
        },
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
    [form, vacancyId],
  );

  // Ждём список вакансий, чтобы подборка не стартовала без стартовых фильтров вакансии.
  const ready = !vacancyId || vacancy !== null || vacancies.isError;
  const formKey = JSON.stringify(form);
  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => run(null), 150);
    return () => clearTimeout(t);
  }, [formKey, vacancyId, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof SearchForm>(k: K, v: SearchForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  const reset = () => {
    setForm(vacancyForm(vacancy, form.sort));
    setChips(null);
  };
  const pickVacancy = (id: string) => {
    if (pathVacancy) navigate(id ? `/employer/vacancies/${id}/shortlist` : "/employer/search");
    else setParams(id ? { vacancy: id } : {});
    if (!id) setForm(EMPTY_FORM);
  };

  const submitQuery = () => {
    setParseError(null);
    parse.mutate(
      { data: { text: query.trim().slice(0, 500) } },
      {
        onSuccess: (r) => {
          if (r.status !== 200) return setParseError(T.parseFailed);
          setForm((f) => fromParsed(r.data.filters, f.sort));
          setChips(r.data.chips ?? []);
          setParseKey((k) => k + 1);
        },
        onError: () => setParseError(T.parseFailed),
      },
    );
  };
  const visibleChips = chips ? chips.filter((c) => chipActive(c, form)) : null;

  const react = (c: CandidateCard, event: Feedback) => {
    if (session.current) feedback.mutate({ data: { session_id: session.current, candidate_pseudo_id: c.pseudo_id, event } });
  };
  const toggleShortlist = (c: CandidateCard) => {
    const on = !shortlisted.has(c.pseudo_id);
    setShortlisted((s) => {
      const n = new Set(s);
      if (on) n.add(c.pseudo_id);
      else n.delete(c.pseudo_id);
      return n;
    });
    if (on) react(c, "shortlist");
  };
  const dismiss = (c: CandidateCard) => {
    setDismissed((s) => new Set(s).add(c.pseudo_id));
    react(c, "dismiss");
  };
  const open = (c: CandidateCard) => {
    react(c, "open");
    const q = vacancyId ? `?vacancy=${vacancyId}&source=match` : "?source=search";
    navigate(`/employer/candidates/${c.pseudo_id}${q}`);
  };

  const shown = items.filter((c) => !dismissed.has(c.pseudo_id));
  const pending = search.isPending;
  const panel = (
    <SearchFiltersPanel
      form={form}
      set={set}
      onReset={reset}
      vacancies={myVacancies}
      vacancyId={vacancyId}
      onPickVacancy={pickVacancy}
      skills={taxSkills}
      skillName={skillName}
    />
  );

  return (
    <div className={cn(PAGE.normal, "gap-6")}>
      <header className={vacancy ? "grid gap-1" : "sr-only"}>
        <h1 className="font-mono text-24 font-semibold">{vacancy ? T.shortlistTitle(vacancy.title) : T.title}</h1>
        <p className="text-14 text-muted">{T.anon}</p>
      </header>

      <QueryBar
        value={query}
        onChange={setQuery}
        onSubmit={submitQuery}
        pending={parse.isPending}
        chips={visibleChips}
        parseKey={parseKey}
        error={parseError}
        onRemoveChip={(c) => setForm((f) => removeChip(c, f))}
      />

      <div className="grid items-start gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="hidden rounded-xl border border-hairline bg-card p-5 lg:block">{panel}</aside>

        <section aria-label="Выдача" className="grid min-w-0 gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h2 role="status" className="mr-auto font-mono text-20 font-semibold">
              {pending && items.length === 0 ? T.searching : total !== null ? T.found(total) : T.searching}
            </h2>
            <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
              <SheetTrigger asChild>
                <Button variant="outline" size="sm" className="lg:hidden">
                  <SlidersHorizontal aria-hidden className="size-4" />
                  {T.filters}
                </Button>
              </SheetTrigger>
              <SheetContent side="right" aria-describedby={undefined}>
                <SheetTitle className="sr-only">{T.filters}</SheetTitle>
                {/* Отступ сверху: крестик Sheet не наезжает на «Сбросить». */}
                <div className="pt-8">{panel}</div>
              </SheetContent>
            </Sheet>
            <div className="flex items-center gap-2 text-13 text-muted">
              <span className="hidden sm:inline">{T.sort}</span>
              <Select
                className="w-48 text-ink"
                value={form.sort ?? "match"}
                onChange={(v) => v && set("sort", v as SearchRequestSort)}
                aria-label={T.sort}
                options={Object.entries(SORT_LABEL).map(([k, v]) => ({ value: k, label: v }))}
              />
            </div>
          </div>

          {failed && <ErrorState title={T.failed} onRetry={() => run(null)} />}

          {pending && items.length === 0 && !failed && (
            <div className="grid gap-4" aria-hidden>
              <Skeleton className="h-64 rounded-xl" />
              <Skeleton className="h-64 rounded-xl" />
            </div>
          )}

          {total === 0 && !pending && !failed && <EmptyState title={T.empty} description={T.emptyHint} />}

          <ul className="grid gap-4">
            {shown.map((c) => (
              <li key={c.pseudo_id}>
                <CandidateCardView
                  c={toCardData(c)}
                  shortlisted={shortlisted.has(c.pseudo_id)}
                  onShortlist={() => toggleShortlist(c)}
                  onReject={() => dismiss(c)}
                  onOpen={() => open(c)}
                  onInterest={() => setInterestFor(c)}
                />
              </li>
            ))}
          </ul>

          {cursor && (
            <Button variant="outline" onClick={() => run(cursor)} loading={pending} className="justify-self-center">
              {pending ? T.loadingMore : T.more}
            </Button>
          )}
        </section>
      </div>
      {interestFor && (
        <OfferDialog
          open
          onOpenChange={(v) => !v && setInterestFor(null)}
          mode="interest"
          candidate={{ pseudoId: interestFor.pseudo_id, pseudonym: interestFor.pseudonym, salaryMin: interestFor.salary_min ?? null }}
          vacancyId={vacancyId ?? ""}
        />
      )}
    </div>
  );
}
