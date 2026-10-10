import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { Bookmark, Button, Chips, EmptyState, ErrorState, GradeTag, H2, Lbl, MatchRingV2, PanelCap, SkillTag, cardInteractive, cn } from "@fsp/ui";

import { searchCandidatesSearchCandidatesPost } from "@/api/endpoints/search/search";
import { useShortlistAddNeedsNeedIdShortlistPseudoIdPost, useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete } from "@/api/endpoints/needs/needs";
import type { CandidateCard, SearchFilters } from "@/api/model";
import { toMatchCard } from "./match-model";
import { FIND_TEXT as F, MATCH_TEXT as T } from "./text";

const PAGE_SIZE = 12;

/** Шорт-лист потребности: множество pseudo_id, оптимистичное переключение, откат при ошибке. */
export function useShortlist(needId: string | null) {
  const [ids, setIds] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState(false);
  const add = useShortlistAddNeedsNeedIdShortlistPseudoIdPost();
  const remove = useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete();

  /** Добавить известные серверу id (из ответа категорий или флагов карточек). */
  const seed = useCallback((more: Iterable<string>) => {
    setIds((old) => {
      const s = new Set(old);
      for (const x of more) s.add(x);
      return s;
    });
  }, []);

  const toggle = (id: string) => {
    if (!needId) return;
    const on = !ids.has(id);
    setFailed(false);
    setIds((s) => {
      const n = new Set(s);
      if (on) n.add(id);
      else n.delete(id);
      return n;
    });
    const revert = () => {
      setFailed(true);
      setIds((s) => {
        const n = new Set(s);
        if (on) n.delete(id);
        else n.add(id);
        return n;
      });
    };
    (on ? add : remove).mutate({ needId, pseudoId: id }, { onError: revert });
  };
  return { ids, toggle, seed, failed, enabled: !!needId };
}

export type ShortlistApi = ReturnType<typeof useShortlist>;

/**
 * Карточка кандидата для подбора (E41-11): только главное — псевдоним, грейд, вилка, совпадение, 3 навыка.
 * Подробности — по клику (вся карточка ведёт в профиль); кнопка «В шорт-лист» видна всегда и не открывает профиль.
 */
export function CandidateTile({ card, profession, shortlist }: { card: CandidateCard; profession: string; shortlist: ShortlistApi }) {
  const d = toMatchCard(card, profession);
  const on = shortlist.ids.has(card.pseudo_id);
  return (
    <article aria-label={d.pseudonym} className={cn("relative flex w-full min-w-0 flex-col gap-3 rounded-xl border border-hairline bg-card p-4", cardInteractive)}>
      <div className="flex items-center gap-3">
        <MatchRingV2 value={d.match} size={48} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <Link
            to={`/employer/candidates/${card.pseudo_id}?source=match`}
            aria-label={`${d.pseudonym}: ${F.open.toLowerCase()} профиль`}
            className="truncate font-mono text-16 font-semibold text-ink after:absolute after:inset-0 after:content-[''] focus-visible:outline-2 focus-visible:outline-brand"
          >
            {d.pseudonym}
          </Link>
          <span className="flex flex-wrap items-center gap-1.5">
            <GradeTag claimed={!d.confirmed}>{d.grade}</GradeTag>
          </span>
        </div>
        {d.salary && <span className="num shrink-0 text-15 font-semibold whitespace-nowrap">{d.salary}</span>}
      </div>
      {d.skills.length > 0 && (
        <Chips>
          {d.skills.map((s) => (
            <SkillTag key={s.name} name={s.name} level={s.level} state={s.claimed ? "claimed" : "confirmed"} />
          ))}
        </Chips>
      )}
      {shortlist.enabled && (
        <Button
          variant={on ? "default" : "outline"}
          size="sm"
          aria-pressed={on}
          data-testid="shortlist-toggle"
          onClick={() => shortlist.toggle(card.pseudo_id)}
          className="relative z-10 w-fit"
        >
          <Bookmark aria-hidden className="size-4" fill={on ? "currentColor" : "none"} />
          {on ? F.shortlisted : F.shortlist}
        </Button>
      )}
    </article>
  );
}

/** Сетка карточек. */
export function CandidateGrid({ items, profession, shortlist, label }: { items: CandidateCard[]; profession: (c: CandidateCard) => string; shortlist: ShortlistApi; label: string }) {
  return (
    <ul aria-label={label} className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2 2xl:grid-cols-3" data-testid="match-top">
      {items.map((c) => (
        <li key={c.pseudo_id} className="flex min-w-0">
          <CandidateTile card={c} profession={profession(c)} shortlist={shortlist} />
        </li>
      ))}
    </ul>
  );
}

/** Режим «Кандидаты»: список кандидатов по условиям запроса сразу, без выбора категории. */
export function CandidateList({ filters, filtersKey, shortlist }: { filters: SearchFilters; filtersKey: string; shortlist: ShortlistApi }) {
  const [items, setItems] = useState<CandidateCard[]>([]);
  const [total, setTotal] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const seq = useRef(0);
  const session = useRef<string | null>(null);
  const { seed } = shortlist;

  const load = useCallback(
    async (next: string | null) => {
      const n = ++seq.current;
      setState("loading");
      try {
        const r = await searchCandidatesSearchCandidatesPost({ filters, sort: "match", limit: PAGE_SIZE, cursor: next, session_id: next ? session.current : null });
        if (n !== seq.current) return;
        if (r.status !== 200) return setState("error");
        session.current = r.data.session_id ?? null;
        setItems((old) => (next ? [...old, ...r.data.items] : r.data.items));
        setCursor(r.data.next_cursor ?? null);
        setTotal(r.data.total ?? r.data.items.length);
        seed(r.data.items.filter((c) => c.is_shortlisted).map((c) => c.pseudo_id));
        setState("ready");
      } catch {
        if (n === seq.current) setState("error");
      }
    },
    [filters, seed],
  );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void load(null), [filtersKey]);

  let body;
  if (state === "error" && items.length === 0) body = <ErrorState title={F.candidatesFailed} onRetry={() => void load(null)} />;
  else if (state === "ready" && items.length === 0) body = <EmptyState title={F.candidatesEmpty} description={F.candidatesEmptyHint} />;
  else if (items.length === 0) body = <div className="h-40 animate-pulse rounded-xl bg-tint-50" aria-hidden />;
  else
    body = (
      <>
        <CandidateGrid items={items} profession={(c) => c.primary_role ?? ""} shortlist={shortlist} label={F.candidates} />
        {cursor && (
          <Button variant="outline" onClick={() => void load(cursor)} loading={state === "loading"} className={cn("self-center")}>
            {F.moreCandidates}
          </Button>
        )}
      </>
    );
  return (
    <section aria-label={F.candidates} className="flex flex-col gap-3" data-testid="match-candidates">
      <PanelCap className="mb-0" title={<H2>{F.candidates}</H2>} aside={state === "ready" ? <Lbl>{T.people(total)}</Lbl> : undefined} />
      {body}
    </section>
  );
}
