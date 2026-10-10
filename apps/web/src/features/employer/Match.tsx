import { PAGE } from "@/shared/lib/page";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import {
  Button,
  buttonVariants,
  cn,
  EmptyState,
  ErrorState,
  FeedEvent,
  FeedList,
  formatRub,
  H2,
  Lbl,
  ListRow,
  MeterBar,
  Panel,
  PanelCap,
  SegmentedControl,
  Sheet,
  SheetContent,
  SheetTitle,
  SheetTrigger,
  Skeleton,
  SlidersHorizontal,
  StatusTag,
  X,
} from "@fsp/ui";

import { useEmployerActivityEmployerActivityGet } from "@/api/endpoints/employer/employer";
import { useCategoryCandidatesCategoriesProfessionGradeCandidatesGet, useCreateNeedNeedsPost, useNeedCategoriesNeedsNeedIdCategoriesGet } from "@/api/endpoints/needs/needs";
import { useSearchParseSearchParsePost } from "@/api/endpoints/search/search";
import { useListSubscriptionsSubscriptionsGet } from "@/api/endpoints/subscriptions/subscriptions";
import { useSuggestProfessionsTaxonomyProfessionsSuggestGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { ActivityEvent, CandidateCard, NeedCategory } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { GRADE_LABEL, ROLE_LABEL } from "@/features/profile/text";
import { Gi } from "@/shared/Gloss";
import { useAuth } from "@/shared/lib/auth";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import { useSkillSource } from "@/shared/lib/skills";
import {
  catKey,
  categoryStats,
  categoryTitle,
  feedTime,
  isToday,
  loadLastNeed,
  onboardingSkipped,
  pickCategory,
  saveLastNeed,
  setOnboardingSkipped,
  subscriptionTerms,
  subscriptionTitle,
} from "./match-model";
import { CandidateGrid, CandidateList, useShortlist, type ShortlistApi } from "./MatchCards";
import { MatchFilters } from "./MatchFilters";
import { EmployerOnboarding } from "./Onboarding";
import { EMPTY_CRITERIA, criteriaKey, criteriaParams, filterCount, hasSubject, isEmpty, mergeFilters, parseCriteria, toNeedFilters, type Criteria } from "./query-model";
import { TagQuery } from "./TagQuery";
import { chipText } from "./search-model";
import { FEED_TEXT, FIND_TEXT as F, FORMAT_LABEL, MATCH_TEXT as T } from "./text";

const PAGE_SIZE = 12;
const FEED_LIMIT = 8;

type Condition = { key: string; label: string; drop: Criteria };

/** Включённые фильтры панели: подпись и как снять — для строки «Условия». */
function conditions(c: Criteria): Condition[] {
  const out: Condition[] = [];
  if (c.grades.length) {
    const first = GRADE_LABEL[c.grades[0]!] ?? c.grades[0]!;
    const last = GRADE_LABEL[c.grades[c.grades.length - 1]!] ?? "";
    out.push({ key: "grade", label: c.grades.length > 1 ? `${first}–${last}` : first, drop: { ...c, grades: [] } });
  }
  if (c.confirmed) out.push({ key: "confirmed", label: F.confirmed, drop: { ...c, confirmed: false } });
  if (c.trust !== null) out.push({ key: "trust", label: `${F.trust} ${"●".repeat(c.trust)}${"○".repeat(4 - c.trust)}`, drop: { ...c, trust: null } });
  if (c.fsp) out.push({ key: "fsp", label: F.fspOnly, drop: { ...c, fsp: false } });
  for (const city of c.cities) out.push({ key: `city:${city}`, label: city, drop: { ...c, cities: c.cities.filter((x) => x !== city) } });
  if (c.relocation) out.push({ key: "reloc", label: F.relocation, drop: { ...c, relocation: false } });
  if (c.salaryFrom !== null || c.salaryTo !== null) {
    const label = [c.salaryFrom !== null ? `от ${formatRub(c.salaryFrom)}` : null, c.salaryTo !== null ? `до ${formatRub(c.salaryTo)}` : null].filter(Boolean).join(" ");
    out.push({ key: "salary", label, drop: { ...c, salaryFrom: null, salaryTo: null } });
  }
  for (const f of c.formats) out.push({ key: `format:${f}`, label: FORMAT_LABEL[f] ?? f, drop: { ...c, formats: c.formats.filter((x) => x !== f) } });
  return out;
}

/** «Условия»: включённые фильтры чипсами с крестиком и «Сбросить всё» (навыки и профессия остаются). */
function Conditions({ c, onChange }: { c: Criteria; onChange: (next: Criteria) => void }) {
  const items = conditions(c);
  if (items.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="match-chips">
      <Lbl className="mr-1">{F.active}</Lbl>
      <ul aria-label={F.active} className="m-0 flex min-w-0 list-none flex-wrap gap-2 p-0">
        {items.map((x) => (
          <li key={x.key} className="inline-flex h-7 max-w-full items-center gap-1 rounded-md border border-tint-200 bg-tint-50 pl-2 pr-0.5 font-mono text-12 font-medium text-chip-fg">
            <span className="truncate">{x.label}</span>
            <button
              type="button"
              onClick={() => onChange(x.drop)}
              aria-label={`Убрать условие «${x.label}»`}
              className="inline-flex size-6 items-center justify-center rounded-sm text-muted hover:bg-tint-100 hover:text-ink focus-visible:outline-2 focus-visible:outline-brand"
            >
              <X aria-hidden className="size-3.5" />
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={() => onChange({ ...EMPTY_CRITERIA, skills: c.skills, profession: c.profession })}
        className="min-h-8 rounded-md px-1 text-13 font-medium text-brand-fg hover:underline focus-visible:outline-2 focus-visible:outline-brand"
      >
        {F.resetAll}
      </button>
    </div>
  );
}

/** Плитка категории (E41-11): профессия, грейд, вилка, совпадение, 3 навыка; подробности — «Почему эти категории». */
function CategoryTile({ c, on, onSelect }: { c: NeedCategory; on: boolean; onSelect: () => void }) {
  const s = categoryStats(c);
  const affinity = Math.round(c.affinity * 100);
  const skills = (c.matched_skills ?? []).slice(0, 3);
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onSelect}
      className={cn(
        "flex w-72 shrink-0 flex-col gap-3 rounded-xl border p-4 text-left hover:border-brand-mid focus-visible:outline-2 focus-visible:outline-brand md:w-full",
        on ? "border-brand bg-tint-50" : "border-hairline bg-card",
      )}
    >
      <span className="grid grid-cols-[minmax(0,1fr)_64px] items-center gap-x-3">
        <b className={cn("truncate font-mono text-16 font-semibold", c.candidates === 0 && !on && "text-muted")}>{categoryTitle(c)}</b>
        <MeterBar value={affinity} label={T.affinity(affinity)} />
      </span>
      <span className="num text-14 text-muted">
        <span className="text-ink">{s.people}</span> {T.peopleShort} · <span className="text-ink">{s.median}</span> · <span className="text-ink">{s.fsp}</span> {T.fsp}
      </span>
      {skills.length > 0 && (
        <span className="flex flex-wrap gap-1.5">
          {skills.map((k) => (
            <span key={k} className="rounded-md border border-tint-200 bg-tint-50 px-2 py-0.5 font-mono text-12 text-chip-fg">
              {k}
            </span>
          ))}
        </span>
      )}
    </button>
  );
}

/** «Почему эти категории»: какие навыки запроса есть у профессии, названа ли она, откуда грейды. */
function Why({ cats, grades }: { cats: NeedCategory[]; grades: string[] }) {
  const profs = [...new Map(cats.map((c) => [c.profession, c])).values()];
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-tint-50 p-3 text-13" data-testid="match-why">
      <p className="text-muted">{F.whyLead}</p>
      <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
        {profs.map((c) => {
          const skills = c.matched_skills ?? [];
          const reasons = [
            c.named ? F.whyNamed : null,
            skills.length ? F.whySkills(skills.join(", ")) : c.named ? null : F.whyNoSkills,
            skills.length ? F.whyMatch(Math.round(c.affinity * 100)) : null,
          ].filter(Boolean);
          return (
            <li key={c.profession}>
              <b className="font-mono font-semibold">{c.title}</b> — {reasons.join(" · ")}
            </li>
          );
        })}
      </ul>
      <p className="text-muted">{grades.length ? F.whyGrades(grades.map((g) => GRADE_LABEL[g] ?? g).join(", ")) : F.whyAllGrades}</p>
    </div>
  );
}

/** Категории запроса: непустые сразу, пустые — по кнопке; под ними — «Почему эти категории». */
function Categories({ cats, selected, onSelect, grades }: { cats: NeedCategory[]; selected: string | null; onSelect: (c: NeedCategory) => void; grades: string[] }) {
  const [showEmpty, setShowEmpty] = useState(false);
  const [why, setWhy] = useState(true);
  const full = cats.filter((c) => c.candidates > 0 || catKey(c) === selected);
  const empty = cats.length - full.length;
  const shown = showEmpty || full.length === 0 ? cats : full;
  return (
    <Panel aria-label={F.categories} data-testid="match-categories" className="flex flex-col gap-3">
      <PanelCap
        className="mb-0"
        title={
          <span className="flex items-center gap-1">
            <H2>{F.categories}</H2>
            <Gi k="category" />
          </span>
        }
        aside={<Lbl>{F.categoriesCount(cats.length)}</Lbl>}
      />
      <ul className="-mx-1 m-0 flex list-none gap-2 overflow-x-auto px-1 pb-1 md:grid md:grid-cols-2 md:overflow-visible">
        {shown.map((c) => (
          <li key={catKey(c)} className="flex">
            <CategoryTile c={c} on={catKey(c) === selected} onSelect={() => onSelect(c)} />
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {empty > 0 && full.length > 0 && (
          <button type="button" onClick={() => setShowEmpty((v) => !v)} className="min-h-8 text-13 font-medium text-brand-fg hover:underline">
            {showEmpty ? F.hideEmpty : F.emptyCats(empty)}
          </button>
        )}
        <button type="button" aria-expanded={why} onClick={() => setWhy((v) => !v)} className="min-h-8 text-13 font-medium text-brand-fg hover:underline">
          {F.why}
        </button>
      </div>
      {why && <Why cats={cats} grades={grades} />}
    </Panel>
  );
}

function CardsSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2" aria-hidden>
      {[0, 1, 2, 3].map((i) => (
        <Panel key={i} className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <Skeleton className="size-11 rounded-full" />
            <div className="flex flex-1 flex-col gap-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-6 w-2/3" />
        </Panel>
      ))}
    </div>
  );
}

/** Компактная подборка выбранной категории: грейд, топ-3 навыка, совпадение, ожидания; «Все N» — в категорию. */
function Candidates({ needId, category, shortlist }: { needId: string; category: NeedCategory; shortlist: ShortlistApi }) {
  const q = useCategoryCandidatesCategoriesProfessionGradeCandidatesGet(
    category.profession,
    category.grade,
    { need_id: needId, limit: PAGE_SIZE },
    { query: { enabled: category.candidates > 0 } },
  );
  const page = q.data?.status === 200 ? q.data.data : undefined;
  const total = page?.total ?? category.candidates;
  const href = `/employer/categories/${category.profession}/${category.grade}?need_id=${needId}`;
  const { seed } = shortlist;
  useEffect(() => {
    if (page) seed(page.items.filter((c: CandidateCard) => c.is_shortlisted).map((c: CandidateCard) => c.pseudo_id));
  }, [page, seed]);
  let body: ReactNode;
  if (category.candidates === 0 || (page && page.items.length === 0))
    body = (
      <EmptyState
        title={F.noCandidates}
        description={F.noCandidatesHint}
        action={
          <Link to="/employer/subscriptions" className={buttonVariants({ variant: "outline" })}>
            {T.subscribe}
          </Link>
        }
      />
    );
  else if (q.isError) body = <ErrorState title={T.candidatesFailed} onRetry={() => void q.refetch()} />;
  else if (!page) body = <CardsSkeleton />;
  else
    body = (
      <CandidateGrid items={page.items} profession={() => category.profession} shortlist={shortlist} label={F.candidates} />
    );
  return (
    <section aria-label={F.candidates} className="flex flex-col gap-3">
      <PanelCap
        className="mb-0"
        title={<H2>{`${F.candidates} · ${categoryTitle(category)}`}</H2>}
        aside={
          page && total > page.items.length ? (
            <Link to={href} className="text-13 font-semibold text-brand-fg hover:underline" data-testid="match-all">
              {F.allInCategory(total)}
            </Link>
          ) : (
            <Lbl>{T.people(total)}</Lbl>
          )
        }
      />
      {body}
    </section>
  );
}

function FeedText({ e }: { e: ActivityEvent }) {
  const tail = (FEED_TEXT[e.kind] ?? (() => ""))(e.detail ?? null);
  return (
    <>
      <Link to={e.link} className="font-semibold text-ink hover:underline">
        {displayPseudonym(e.candidate.pseudonym, e.candidate.primary_role)}
      </Link>{" "}
      {tail}
    </>
  );
}

/** Пустая лента: что здесь появится и что сделать, чтобы она ожила. */
function FeedEmpty({ hint, action }: { hint: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2" data-testid="match-feed-empty">
      <p className="text-13 font-semibold">{T.feedEmpty}</p>
      <p className="text-13 text-muted">{hint}</p>
      {action}
    </div>
  );
}

/** Лента активности компании (E35-12b): интересы, приглашения, новые по подпискам. */
function FeedPanel({ hasCompany }: { hasCompany: boolean }) {
  const q = useEmployerActivityEmployerActivityGet({ limit: FEED_LIMIT }, { query: { enabled: hasCompany, retry: false } });
  const items = q.data?.status === 200 ? q.data.data.items : [];
  const today = items[0] && isToday(items[0].at);
  return (
    <Panel aria-label={T.feed} data-testid="match-feed">
      <PanelCap title={T.feed} aside={today ? <Lbl>{T.today}</Lbl> : undefined} />
      {!hasCompany && <FeedEmpty hint={T.feedNoCompanyHint} />}
      {hasCompany && q.isPending && (
        <div className="flex flex-col gap-3" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-3.5" />
          ))}
        </div>
      )}
      {q.isError && <ErrorState title={T.feedFailed} onRetry={() => void q.refetch()} className="p-4" />}
      {q.isSuccess && items.length === 0 && (
        <FeedEmpty
          hint={T.feedEmptyHint}
          action={
            <Link to="/employer/subscriptions" className={cn(buttonVariants({ variant: "outline" }), "h-auto min-h-9 whitespace-normal py-1.5 text-center sm:h-auto")}>
              {T.subscribe}
            </Link>
          }
        />
      )}
      {items.length > 0 && (
        <FeedList label={T.feed}>
          {items.map((e) => (
            <FeedEvent key={e.id} time={feedTime(e.at)}>
              <FeedText e={e} />
            </FeedEvent>
          ))}
        </FeedList>
      )}
    </Panel>
  );
}

/** Подписки компании: категория, условия, «только подтверждённые» — строкой, ведут к управлению подписками. */
function SubscriptionsPanel() {
  const q = useListSubscriptionsSubscriptionsGet({ query: { retry: false } });
  const subs = q.data?.status === 200 ? q.data.data : [];
  if (q.isSuccess && subs.length === 0)
    return (
      <Panel aria-label={T.subscriptions} data-testid="match-subscriptions-empty">
        <PanelCap title={T.subscriptions} />
        <div className="flex flex-col items-start gap-2">
          <p className="text-13 font-semibold">{T.subscriptionsEmpty}</p>
          <p className="text-13 text-muted">{T.subscriptionsEmptyHint}</p>
          <Link to="/employer/subscriptions" className={cn(buttonVariants({ variant: "outline" }), "h-auto min-h-9 whitespace-normal py-1.5 text-center sm:h-auto")}>
            {T.subscribe}
          </Link>
        </div>
      </Panel>
    );
  if (subs.length === 0) return null;
  return (
    <Panel aria-label={T.subscriptions} data-testid="match-subscriptions">
      <PanelCap
        title={
          <H2>
            <Link to="/employer/subscriptions" className="hover:underline">
              {T.subscriptions}
            </Link>
          </H2>
        }
        aside={<Lbl>{subs.length}</Lbl>}
      />
      {subs.map((s) => (
        <ListRow key={s.id}>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <b className="truncate font-mono text-14 font-semibold">{subscriptionTitle(s)}</b>
            <span className="text-12 text-muted">{subscriptionTerms(s)}</span>
          </div>
          <StatusTag state={s.only_confirmed ? "confirmed" : "claimed"}>{s.only_confirmed ? T.onlyConfirmed : T.anyConfirmed}</StatusTag>
        </ListRow>
      ))}
    </Panel>
  );
}

/** Первый вход без запросов: три примера, клик подставляет и отправляет. */
function Examples({ onPick, disabled }: { onPick: (text: string) => void; disabled: boolean }) {
  return (
    <Panel aria-label={T.examples} data-testid="match-examples">
      <PanelCap title={T.examples} />
      <ul className="m-0 flex list-none flex-col gap-2 p-0">
        {T.exampleList.map((x) => (
          <li key={x}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(x)}
              className="w-full rounded-lg border border-hairline px-3 py-2.5 text-left text-14 hover:border-brand hover:bg-tint-50 disabled:opacity-60"
            >
              {x}
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}


/**
 * Подбор работодателя `/employer` (E38-8, E39-21 — поиск сотрудников). Строка запроса с тегами (навыки и
 * профессия из подсказок системы, фраза — в условия через `/search/parse`) и панель фильтров живут в URL;
 * условия → `POST /needs` (`?need=<id>`) → категории с объяснением «почему» → компактная подборка.
 * Справа — подписки и лента. Без условий — примеры запросов.
 */
export default function MatchPage() {
  const { me } = useAuth();
  const navigate = useNavigate();
  // Новая компания (E39-7): онбординг из трёх шагов, пока её нет и его не пропускали.
  const [wizard, setWizard] = useState(() => !me?.company && !onboardingSkipped());
  if (wizard)
    return (
      <EmployerOnboarding
        onSkip={() => {
          setOnboardingSkipped(true);
          setWizard(false);
        }}
        onDone={(needId) => {
          setOnboardingSkipped(true);
          setWizard(false);
          if (needId) navigate(`/employer?need=${needId}`, { replace: true });
        }}
      />
    );
  return <Match hasCompany={!!me?.company} companyId={me?.company?.id} onSetup={() => setWizard(true)} />;
}

function Match({ hasCompany, companyId, onSetup }: { hasCompany: boolean; companyId?: string; onSetup: () => void }) {
  const [params, setParams] = useSearchParams();
  const criteria = useMemo(() => parseCriteria(params), [params]);
  const key = criteriaKey(criteria);
  const needId = params.get("need");
  const subject = hasSubject(criteria);
  const view: "categories" | "candidates" = params.get("view") === "candidates" ? "candidates" : "categories";
  const viewExtra = view === "candidates" ? { view } : {};

  const [labels, setLabels] = useState<Record<string, string>>({});
  const { nameOf, suggest } = useSkillSource(criteria.profession ?? undefined);
  const profsQ = useSuggestProfessionsTaxonomyProfessionsSuggestGet({ q: "", limit: 50 }, { query: { staleTime: 5 * 60_000 } });
  const professions = useMemo(() => (profsQ.data?.status === 200 ? profsQ.data.data.map((p) => ({ slug: p.slug, title: p.title })) : []), [profsQ.data]);

  const catsQ = useNeedCategoriesNeedsNeedIdCategoriesGet(needId ?? "", { query: { enabled: hasCompany && !!needId, retry: false } });
  const cats = useMemo(() => (catsQ.data?.status === 200 ? catsQ.data.data.categories : []), [catsQ.data]);
  const lost = catsQ.isError && catsQ.error instanceof ApiError && catsQ.error.status === 404;
  const selected = pickCategory(cats, params.get("cat"));
  const shortlist = useShortlist(needId);
  const { seed: seedShortlist } = shortlist;
  const serverShortlist = catsQ.data?.status === 200 ? catsQ.data.data.shortlist : undefined;
  useEffect(() => {
    if (serverShortlist) seedShortlist(serverShortlist);
  }, [serverShortlist, seedShortlist]);

  const setView = (v: string) => {
    const next = new URLSearchParams(params);
    next.delete("cat");
    if (v === "candidates") next.set("view", v);
    else next.delete("view");
    setParams(next);
  };

  const skillName = useCallback((s: string) => labels[s] ?? nameOf(s), [labels, nameOf]);
  const professionName = useCallback(
    (s: string) => professions.find((p) => p.slug === s)?.title ?? cats.find((c) => c.profession === s)?.title ?? ROLE_LABEL[s] ?? s,
    [professions, cats],
  );

  /** Новые условия — новая ссылка: потребность и выбранная категория сбрасываются. */
  const update = useCallback((next: Criteria) => setParams(criteriaParams(next, viewExtra)), [setParams, view]); // eslint-disable-line react-hooks/exhaustive-deps

  // Вход без условий: восстанавливаем последний запрос этого браузера (или условия запроса из `?need=`).
  const restored = useRef(false);
  useEffect(() => {
    if (restored.current || !hasCompany) return;
    restored.current = true;
    if (!isEmpty(criteria)) return;
    const last = loadLastNeed(companyId);
    if (!last || (needId && needId !== last.id)) return;
    const next = new URLSearchParams(last.qs ?? "");
    next.set("need", last.id);
    if (view === "candidates") next.set("view", view);
    const cat = params.get("cat");
    if (cat) next.set("cat", cat);
    setParams(next, { replace: true });
  }, [hasCompany]); // eslint-disable-line react-hooks/exhaustive-deps

  // Потребность пропала (удалена или чужая): забываем её; с условиями — строим заново.
  useEffect(() => {
    if (!lost) return;
    if (loadLastNeed(companyId)?.id === needId) saveLastNeed(null);
    setParams(criteriaParams(criteria, viewExtra), { replace: true });
  }, [lost]); // eslint-disable-line react-hooks/exhaustive-deps

  // Условия без потребности → POST /needs (с задержкой: фильтры меняются подряд) → `?need=` в ту же ссылку.
  const create = useCreateNeedNeedsPost();
  const [createError, setCreateError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setCreateError(null);
    if (!hasCompany || needId || !subject) return;
    const t = setTimeout(() => {
      create.mutate(
        { data: { filters: toNeedFilters(criteria) } },
        {
          onSuccess: (r) => {
            if (r.status !== 201) return;
            const id = r.data.id;
            setParams(
              (prev) => {
                const cur = parseCriteria(prev);
                if (criteriaKey(cur) !== key || prev.get("need")) return prev;
                return criteriaParams(cur, { need: id, ...viewExtra });
              },
              { replace: true },
            );
            const chips = [...(criteria.profession ? [professionName(criteria.profession)] : []), ...criteria.skills.map(skillName)];
            saveLastNeed({ id, text: chips.join(", "), chips, company: companyId, qs: key });
          },
          onError: (err) => setCreateError(err instanceof ApiError && err.code === "need_empty" ? F.needSubject : F.failed),
        },
      );
    }, 250);
    return () => clearTimeout(t);
  }, [key, needId, hasCompany, attempt]); // eslint-disable-line react-hooks/exhaustive-deps

  // Фраза целиком → условия (`/search/parse`): навыки и профессия — в строку, остальное — в фильтры.
  const parse = useSearchParseSearchParsePost();
  const [parseMsg, setParseMsg] = useState<string | null>(null);
  const onParse = (text: string) => {
    setParseMsg(null);
    parse.mutate(
      { data: { text: text.trim().slice(0, 500) } },
      {
        onSuccess: (r) => {
          if (r.status !== 200) return setParseMsg(F.parseFailed);
          const learned: Record<string, string> = {};
          for (const ch of r.data.chips ?? []) {
            const v = ch.value as { slug?: string } | string;
            if (ch.key === "skills_must" && typeof v === "object" && v?.slug) learned[v.slug] = chipText(ch);
            if (ch.key === "skills_nice" && typeof v === "string") learned[v] = chipText(ch);
          }
          setLabels((l) => ({ ...l, ...learned }));
          const merged = mergeFilters(criteria, r.data.filters);
          const rest = [...(r.data.unparsed ?? []), ...(r.data.filters.semantic_text ? [r.data.filters.semantic_text] : [])];
          if (criteriaKey(merged) === key) return setParseMsg(F.nothingRecognized);
          if (rest.length) setParseMsg(F.notRecognized(rest.join(", ")));
          update(merged);
        },
        onError: () => setParseMsg(F.parseFailed),
      },
    );
  };

  const select = (c: NeedCategory) => {
    const next = new URLSearchParams(params);
    next.set("cat", catKey(c));
    setParams(next, { replace: true });
  };

  const [sheetOpen, setSheetOpen] = useState(false);
  const reset = () => update({ ...EMPTY_CRITERIA, skills: criteria.skills, profession: criteria.profession });
  const filters = (className?: string) => <MatchFilters c={criteria} onChange={update} onReset={reset} professions={professions} skillSuggest={suggest} skillName={skillName} className={className} />;
  const nFilters = filterCount(criteria);

  let center: ReactNode;
  if (!hasCompany)
    center = (
      <EmptyState
        title={T.noCompany}
        description={T.noCompanyHint}
        action={
          <Button onClick={onSetup} data-testid="match-setup">
            {T.noCompanyAction}
          </Button>
        }
      />
    );
  else if (!needId && isEmpty(criteria)) center = <Examples onPick={onParse} disabled={parse.isPending} />;
  else if (!needId && !subject) center = <EmptyState title={F.needSubject} description={F.queryHint} />;
  else if (createError === F.failed) center = <ErrorState title={F.failed} onRetry={() => setAttempt((a) => a + 1)} />;
  else if (createError) center = <EmptyState title={createError} description={F.queryHint} />;
  else if (!needId || (view === "categories" && catsQ.isPending) || lost) center = <CardsSkeleton />;
  else if (view === "candidates") center = <CandidateList filters={toNeedFilters(criteria)} filtersKey={key} shortlist={shortlist} />;
  else if (catsQ.isError) center = <ErrorState title={T.categoriesLoadFailed} onRetry={() => void catsQ.refetch()} />;
  else if (cats.length === 0) center = <EmptyState title={F.noCategories} description={F.noCategoriesHint} />;
  else
    center = (
      <>
        <Categories cats={cats} selected={selected ? catKey(selected) : null} onSelect={select} grades={criteria.grades} />
        {selected && <Candidates key={`${needId}:${catKey(selected)}`} needId={needId} category={selected} shortlist={shortlist} />}
      </>
    );

  return (
    <div className={PAGE.normal}>
      <h1 className="sr-only">{T.title}</h1>
      {hasCompany && (
        <TagQuery
          skills={criteria.skills}
          profession={criteria.profession}
          skillName={skillName}
          professionName={professionName}
          onSkills={(skills, learned) => {
            setLabels((l) => ({ ...l, ...learned }));
            update({ ...criteria, skills });
          }}
          onProfession={(profession) => update({ ...criteria, profession })}
          onParse={onParse}
          parsing={parse.isPending}
        />
      )}
      {parseMsg && (
        <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-13 text-warning-fg" data-testid="match-parse-msg">
          {parseMsg}
        </p>
      )}

      {hasCompany && (
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl
            label={F.viewLabel}
            value={view}
            onValueChange={setView}
            options={[
              { value: "categories", label: F.viewCategories },
              { value: "candidates", label: F.viewCandidates },
            ]}
          />
          {shortlist.failed && (
            <p role="alert" className="text-13 text-error">
              {F.shortlistFailed}
            </p>
          )}
        </div>
      )}

      <div className={cn("grid items-start gap-4", hasCompany ? "lg:grid-cols-[260px_minmax(0,1fr)] xl:grid-cols-[260px_minmax(0,1fr)_280px]" : "md:grid-cols-[minmax(0,1fr)_280px]")}>
        {hasCompany && <aside className="hidden rounded-xl border border-hairline bg-card p-4 lg:block">{filters()}</aside>}
        <div className="flex min-w-0 flex-col gap-4">
          {hasCompany && (
            <div className="flex flex-wrap items-center gap-2 lg:hidden">
              <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
                <SheetTrigger asChild>
                  <Button variant="outline" size="sm" data-testid="match-filters-open">
                    <SlidersHorizontal aria-hidden className="size-4" />
                    {F.filtersCount(nFilters)}
                  </Button>
                </SheetTrigger>
                <SheetContent side="right" aria-describedby={undefined} className="overflow-y-auto" onOpenAutoFocus={(e) => e.preventDefault()}>
                  <SheetTitle className="sr-only">{F.filters}</SheetTitle>
                  {/* Отступ сверху: крестик Sheet не наезжает на «Сбросить». */}
                  {filters("pt-8")}
                </SheetContent>
              </Sheet>
            </div>
          )}
          {hasCompany && <Conditions c={criteria} onChange={update} />}
          {center}
        </div>
        <div className="flex min-w-0 flex-col gap-4 lg:col-start-2 xl:col-start-auto">
          {hasCompany && needId && <SubscriptionsPanel />}
          <FeedPanel hasCompany={hasCompany} />
        </div>
      </div>
    </div>
  );
}
