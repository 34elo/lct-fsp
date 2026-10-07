import { useEffect, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";

import {
  buttonVariants,
  CandidateCardV2,
  Chips,
  cn,
  EmptyState,
  ErrorState,
  FeedEvent,
  FeedList,
  GradeTag,
  H2,
  Lbl,
  ListRow,
  MatchRingV2,
  MeterBar,
  Panel,
  PanelCap,
  QueryBar,
  Skeleton,
  SkillTag,
  StatusTag,
  Tag,
} from "@fsp/ui";

import { useEmployerActivityEmployerActivityGet } from "@/api/endpoints/employer/employer";
import { useCategoryCandidatesCategoriesProfessionGradeCandidatesGet, useCreateNeedNeedsPost, useNeedCategoriesNeedsNeedIdCategoriesGet } from "@/api/endpoints/needs/needs";
import { useListSubscriptionsSubscriptionsGet } from "@/api/endpoints/subscriptions/subscriptions";
import type { ActivityEvent, CandidateCard, NeedCategory, NeedOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { needChips } from "@/features/needs/NeedCategories";
import {
  catKey,
  categoryStats,
  categoryTitle,
  feedTime,
  isToday,
  loadLastNeed,
  pickCategory,
  salaryShort,
  saveLastNeed,
  subscriptionTerms,
  subscriptionTitle,
  toMatchCard,
} from "./match-model";
import { FEED_TEXT, MATCH_TEXT as T } from "./text";

const TOP = 3;
const RESULTS_LIMIT = 10;
const FEED_LIMIT = 8;

/** Категории потребности `.rw`: название, совпадение с запросом, «37 чел · 220 000 · 24 % ФСП». Клик выбирает категорию. */
function CategoriesPanel({ cats, selected, onSelect, className }: { cats: NeedCategory[]; selected: string | null; onSelect: (c: NeedCategory) => void; className?: string }) {
  return (
    <Panel aria-label={T.categories} className={cn("overflow-hidden p-0", className)} data-testid="match-categories">
      <PanelCap title={T.categories} aside={<Lbl>{cats.length}</Lbl>} className="mb-0 px-3 pt-3.5 pb-2.5" />
      <ul className="m-0 list-none p-0">
        {cats.map((c) => {
          const s = categoryStats(c);
          const on = catKey(c) === selected;
          const affinity = Math.round(c.affinity * 100);
          return (
            <li key={catKey(c)}>
              <button
                type="button"
                aria-pressed={on}
                onClick={() => onSelect(c)}
                className={cn(
                  "grid w-full grid-cols-[minmax(0,1fr)_64px] items-center gap-x-3 gap-y-1 border-t border-hairline px-3 py-2.5 text-left hover:bg-tint-50",
                  on && "bg-tint-50",
                )}
              >
                <b className="truncate font-mono text-14 font-semibold">{categoryTitle(c)}</b>
                <MeterBar value={affinity} label={T.affinity(affinity)} className="row-span-2" />
                <span className="num text-12 text-muted">
                  <span className="text-ink">{s.people}</span> {T.peopleShort} · <span className="text-ink">{s.median}</span> · <span className="text-ink">{s.fsp}</span> {T.fsp}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function CategoriesSkeleton({ className }: { className?: string }) {
  return (
    <Panel className={cn("flex flex-col gap-3", className)} aria-hidden>
      <Skeleton className="h-4 w-32" />
      {[0, 1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-10" />
      ))}
    </Panel>
  );
}

const openLink = (c: CandidateCard) => (
  <Link to={`/employer/candidates/${c.pseudo_id}?source=match`} className={cn(buttonVariants({ variant: "outline" }), "h-9 sm:h-9")}>
    {T.open}
  </Link>
);

/** «Ещё N»: компактные строки после топ-3, заголовок ведёт в категорию целиком. */
function MoreTable({ items, total, profession, href }: { items: CandidateCard[]; total: number; profession: string; href: string }) {
  const cols = "md:grid-cols-[44px_1.2fr_0.7fr_1.5fr_1.1fr]";
  return (
    <Panel className="overflow-hidden p-0" data-testid="match-more">
      <PanelCap
        title={
          <H2>
            <Link to={href} className="hover:underline">
              {T.more(total - TOP)}
            </Link>
          </H2>
        }
        aside={<Lbl>{T.byMatch}</Lbl>}
        className="mb-0 px-4 pt-3.5 pb-2.5"
      />
      <div className={cn("lbl hidden min-h-9 items-center gap-3 px-4 text-muted md:grid", cols)} aria-hidden>
        <span>{T.colMatch}</span>
        <span>{T.colCandidate}</span>
        <span>{T.colGrade}</span>
        <span>{T.colSkills}</span>
        <span className="text-right">{T.colSalary}</span>
      </div>
      <ul className="m-0 list-none p-0">
        {items.map((c) => {
          const d = toMatchCard(c, profession);
          const skill = d.skills[0];
          const grade = <GradeTag claimed={!d.confirmed}>{d.grade}</GradeTag>;
          const chip = skill && <SkillTag name={skill.name} level={skill.level} state={skill.claimed ? "claimed" : "confirmed"} />;
          return (
            <li key={c.pseudo_id}>
              <Link
                to={`/employer/candidates/${c.pseudo_id}?source=match`}
                className={cn("grid min-h-[52px] grid-cols-[34px_minmax(0,1fr)_auto] items-center gap-3 border-t border-hairline px-4 py-2.5 text-ink hover:bg-tint-50", cols)}
              >
                <MatchRingV2 value={d.match} size={34} />
                <span className="flex min-w-0 flex-col gap-1.5">
                  <b className="truncate font-mono text-14 font-semibold">{d.pseudonym}</b>
                  <span className="flex flex-wrap items-center gap-1.5 md:hidden">
                    {grade}
                    {chip}
                  </span>
                </span>
                <span className="hidden justify-self-start md:block">{grade}</span>
                <Chips className="hidden md:flex">{chip}</Chips>
                <span className="num text-right text-13 whitespace-nowrap md:text-14">{salaryShort(c)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}

function MatchesSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-hidden>
      {[0, 1, 2].map((i) => (
        <Panel key={i} className="flex items-center gap-4">
          <Skeleton className="size-11 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </Panel>
      ))}
    </div>
  );
}

/** Топ-3 выбранной категории; в выдаче по запросу — ещё строки «Ещё N». */
function Matches({ needId, category, results }: { needId: string; category: NeedCategory; results: boolean }) {
  const q = useCategoryCandidatesCategoriesProfessionGradeCandidatesGet(
    category.profession,
    category.grade,
    { need_id: needId, limit: results ? RESULTS_LIMIT : TOP },
    { query: { enabled: category.candidates > 0 } },
  );
  const page = q.data?.status === 200 ? q.data.data : undefined;
  const href = `/employer/categories/${category.profession}/${category.grade}?need_id=${needId}`;
  const total = page?.total ?? category.candidates;

  const head = (
    <PanelCap title={T.best} aside={<Lbl>{results ? T.people(total) : T.top3}</Lbl>} className="mb-0" />
  );
  if (category.candidates === 0 || (page && page.items.length === 0))
    return (
      <>
        {head}
        <EmptyState
          title={T.nobodyNear}
          description={T.nobodyNearHint}
          action={
            <Link to="/employer/subscriptions" className={buttonVariants({ variant: "outline" })}>
              {T.subscriptions}
            </Link>
          }
        />
      </>
    );
  if (q.isError) return <ErrorState title={T.candidatesFailed} onRetry={() => void q.refetch()} />;
  if (!page)
    return (
      <>
        {head}
        <MatchesSkeleton />
      </>
    );
  const top = page.items.slice(0, TOP);
  const rest = results ? page.items.slice(TOP) : [];
  return (
    <>
      {head}
      <ul aria-label={T.best} className="m-0 flex list-none flex-col gap-3 p-0" data-testid="match-top">
        {top.map((c) => (
          <li key={c.pseudo_id}>
            <CandidateCardV2 wide c={toMatchCard(c, category.profession)} action={openLink(c)} />
          </li>
        ))}
      </ul>
      {rest.length > 0 && total > TOP && <MoreTable items={rest} total={total} profession={category.profession} href={href} />}
    </>
  );
}

function FeedText({ e }: { e: ActivityEvent }) {
  const tail = (FEED_TEXT[e.kind] ?? (() => ""))(e.detail ?? null);
  return (
    <>
      <Link to={e.link} className="font-semibold text-ink hover:underline">
        {e.candidate.pseudonym}
      </Link>{" "}
      {tail}
    </>
  );
}

/** Лента активности компании (E35-12b): интересы, приглашения, новые по подпискам. */
function FeedPanel() {
  const q = useEmployerActivityEmployerActivityGet({ limit: FEED_LIMIT });
  const items = q.data?.status === 200 ? q.data.data.items : [];
  const today = items[0] && isToday(items[0].at);
  return (
    <Panel aria-label={T.feed} data-testid="match-feed">
      <PanelCap title={T.feed} aside={today ? <Lbl>{T.today}</Lbl> : undefined} />
      {q.isPending && (
        <div className="flex flex-col gap-3" aria-hidden>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-3.5" />
          ))}
        </div>
      )}
      {q.isError && <ErrorState title={T.feedFailed} onRetry={() => void q.refetch()} className="p-4" />}
      {q.isSuccess && items.length === 0 && <p className="text-13 text-muted">{T.feedEmpty}</p>}
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
  const q = useListSubscriptionsSubscriptionsGet();
  const subs = q.data?.status === 200 ? q.data.data : [];
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
 * Подбор работодателя `/employer` (E38-8, бриф §6.3). Строка «кого ищете» → `POST /needs` → `?need=<id>`:
 * слева категории потребности, в центре лучшие совпадения выбранной категории, справа подписки и лента.
 * Без `?need` — первый вход: категории последнего запроса (если он был в этом браузере) и топ-3, иначе примеры.
 */
export default function MatchPage() {
  const [params] = useSearchParams();
  // Новый запрос или возврат к первому входу — экран с чистого листа (поле, ошибка).
  return <Match key={params.get("need") ?? ""} />;
}

function Match() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const [last, setLast] = useState(loadLastNeed);
  const needParam = params.get("need");
  const results = needParam !== null;
  const needId = needParam ?? last?.id ?? null;
  const stateNeed = (location.state as { need?: NeedOut } | null)?.need;
  const chips = stateNeed?.id === needId ? needChips(stateNeed) : last?.id === needId ? (last?.chips ?? []) : [];

  const [text, setText] = useState(() => {
    if (!results) return "";
    if (stateNeed?.id === needParam) return stateNeed.text ?? "";
    return last?.id === needParam ? last.text : "";
  });
  const [error, setError] = useState<string | null>(null);
  const create = useCreateNeedNeedsPost();

  const catsQ = useNeedCategoriesNeedsNeedIdCategoriesGet(needId ?? "", { query: { enabled: !!needId, retry: false } });
  const cats = catsQ.data?.status === 200 ? catsQ.data.data.categories : [];
  const lost = catsQ.isError && catsQ.error instanceof ApiError && catsQ.error.status === 404;
  // Запомненный запрос удалён или чужой — забываем его и начинаем с примеров.
  useEffect(() => {
    if (!results && lost) {
      saveLastNeed(null);
      setLast(null);
    }
  }, [results, lost]);
  const selected = pickCategory(cats, params.get("cat"));

  const submit = (value: string) => {
    setError(null);
    create.mutate(
      { data: { text: value } },
      {
        onSuccess: (r) => {
          if (r.status !== 201) return;
          const v = { id: r.data.id, text: value, chips: needChips(r.data) };
          // Экран пересоздаётся по новому `?need` и сам прочитает запомненный запрос.
          saveLastNeed(v);
          setParams({ need: r.data.id }, { state: { need: r.data } });
        },
        onError: (err) => setError(err instanceof ApiError && err.code === "need_empty" ? T.notUnderstood : T.failed),
      },
    );
  };
  const pickExample = (x: string) => {
    setText(x);
    submit(x);
  };
  const select = (c: NeedCategory) => {
    const next = new URLSearchParams(params);
    next.set("cat", catKey(c));
    setParams(next, { replace: true, state: location.state });
  };

  const noNeed = !needId || (lost && !results);
  const showCats = !noNeed && (catsQ.isPending || (catsQ.isSuccess && cats.length > 0));

  let center;
  if (noNeed) center = <Examples onPick={pickExample} disabled={create.isPending} />;
  else if (catsQ.isPending) center = <MatchesSkeleton />;
  else if (lost) center = <EmptyState title={T.nothing} description={T.nothingHint} />;
  else if (catsQ.isError) center = <ErrorState title={T.categoriesLoadFailed} onRetry={() => void catsQ.refetch()} />;
  else if (!selected) center = <EmptyState title={T.nothing} description={T.nothingHint} />;
  else center = <Matches key={`${needId}:${catKey(selected)}`} needId={needId} category={selected} results={results} />;

  return (
    <div className="mx-auto flex w-full max-w-[1328px] flex-col gap-4 px-4 py-4 md:px-6 md:py-6">
      <h1 className="sr-only">{T.title}</h1>
      <QueryBar value={text} onChange={setText} onSubmit={submit} loading={create.isPending} placeholder={T.placeholder} label={T.queryLabel} submitLabel={T.submit} />
      {error && (
        <p role="alert" className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
          {error}
        </p>
      )}

      <div className="grid items-start gap-4 md:grid-cols-12">
        {showCats &&
          (catsQ.isPending ? (
            <CategoriesSkeleton className={cn("md:col-span-3", results && "hidden md:flex")} />
          ) : (
            <CategoriesPanel
              cats={cats}
              selected={selected ? catKey(selected) : null}
              onSelect={select}
              className={cn("md:col-span-3", results && "hidden md:block")}
            />
          ))}
        <div className={cn("flex min-w-0 flex-col gap-3", showCats ? "md:col-span-6" : "md:col-span-9")}>
          {results && chips.length > 0 && (
            <Chips aria-label={T.understood} data-testid="match-chips">
              {chips.map((c) => (
                <Tag key={c}>{c}</Tag>
              ))}
            </Chips>
          )}
          {center}
        </div>
        <div className="flex min-w-0 flex-col gap-4 md:col-span-3">
          {results && <SubscriptionsPanel />}
          <FeedPanel />
        </div>
      </div>
    </div>
  );
}
