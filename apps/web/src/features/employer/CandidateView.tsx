import { PAGE } from "@/shared/lib/page";
import { Gloss } from "@/shared/Gloss";
import {
  Avatar,
  buttonVariants,
  Button,
  Chips,
  Input,
  SegmentedControl,
  ConstellationAvatar,
  dotsText,
  EmptyState,
  ErrorState,
  formatRub,
  FspProtocol,
  GradeTag,
  H1,
  H2,
  Lbl,
  ListRow,
  MatchRingV2,
  MatchWhy,
  Num,
  Panel,
  PanelCap,
  Skeleton,
  SkillTag,
  StatusTag,
  Tag,
  type WhyItem,
} from "@fsp/ui";
import { avatarSrc } from "@/shared/lib/avatar";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import {
  useNeedCategoriesNeedsNeedIdCategoriesGet,
  useShortlistAddNeedsNeedIdShortlistPseudoIdPost,
  useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete,
} from "@/api/endpoints/needs/needs";
import { useCandidateCardCandidatesPseudoIdCardGet } from "@/api/endpoints/search/search";
import type { CandidateCardFull, ClaimedVsConfirmed, SkillWithTrust } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { gradeTitle, professionTitle } from "@/features/needs/need-model";
import { OfferDialog } from "@/features/offers/OfferDialog";
import { EMP_INT_TEXT as IT, OFFER_STATUS_LABEL } from "@/features/offers/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import {
  dedupeExperience,
  filterSkills,
  fspResults,
  kindOf,
  rankSkills,
  skillLevel,
  splitClaimed,
  TOP_SKILLS,
  yearsLabel,
  type SkillFilter,
} from "./candidate-model";
import { FORMAT_LABEL, SEARCH_STATUS_LABEL, SOURCE_SHORT } from "./text";

const T = {
  nav: "Навигация",
  crumbRoot: "Подбор",
  back: "К подбору",
  toCategory: "К категории",
  header: "Шапка карточки",
  expectations: "Ожидания",
  fspVerified: "профиль подтверждён ФСП",
  strength: "сила",
  match: "совпадение",
  rank: (r: number) => `ранг ${r.toFixed(2)}`,
  skills: "Навыки",
  skillsHint: "сплошная — подтверждено · пунктир — заявлено",
  noSkills: "Навыки ещё не указаны.",
  allSkills: (n: number) => `Все навыки (${n})`,
  hideSkills: "Свернуть",
  skillSearch: "Найти навык",
  skillFilter: "Фильтр навыков",
  filterAll: "Все",
  filterConfirmed: "Подтверждённые",
  filterClaimed: "Заявленные",
  nothingFound: "Ничего не найдено — измените запрос или фильтр.",
  claimedCol: "Заявлено кандидатом",
  confirmedCol: "Подтверждено",
  claimedColHint: "Слова кандидата и резюме, без независимого подтверждения",
  confirmedColHint: "Тест, ФСП, GitHub и другие проверяемые источники",
  skillsCount: (n: number) => `${n} навыков`,
  gradeLbl: "Грейд",
  noneClaimed: "Заявленных без подтверждения нет.",
  noneConfirmed: "Подтверждённых навыков пока нет.",
  more: (n: number) => `и ещё ${n}`,
  fspHint: "Сначала соревнования, релевантные профессии кандидата",
  evidence: "Показать связи списком",
  fsp: "Достижения ФСП",
  claimedConfirmed: "Заявлено и подтверждено",
  profession: "Профессия",
  declared: "Заявлен",
  confirmed: "Подтверждён",
  noGrade: "нет",
  experience: "Опыт и компании",
  experienceHidden: "скрыто приватностью",
  experienceHint: "Названия компаний скрыты до раскрытия контактов",
  why: "Почему подходит",
  interestPanel: "Ваш интерес",
  interest: "Интерес",
  invite: "Пригласить",
  shortlist: "В шорт-лист",
  shortlisted: "В шорт-листе",
  shortlistError: "Не удалось изменить шорт-лист.",
  market: "С вашим бюджетом",
  candidateWants: "Ожидания кандидата",
  median: "Медиана категории",
  contacts: "Контакты откроются только после согласия кандидата.",
  hidden: "Профиль недоступен — кандидат скрыл его",
  failed: "Не загрузилось",
};

const WHY_KIND = { plus: "ok", minus: "no", warn: "warn" } as const;

function Skeletons() {
  return (
    <div aria-hidden data-testid="candidate-loading" className="flex flex-col gap-4">
      <Skeleton className="h-[100px] w-full rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        {[5, 4].map((rows) => (
          <Panel key={rows} className="flex flex-col gap-2.5">
            <Skeleton className="h-4 w-2/5" />
            {Array.from({ length: rows }, (_, i) => (
              <Skeleton key={i} className={i === rows - 1 ? "h-3 w-[70%]" : "h-3 w-full"} />
            ))}
          </Panel>
        ))}
      </div>
    </div>
  );
}

function SkillRow({ s }: { s: SkillWithTrust }) {
  return (
    <ListRow>
      <SkillTag name={s.skill.name} state={kindOf(s) === "verified" ? "confirmed" : "claimed"} className="min-w-24" />
      <span aria-label={`доверие ${skillLevel(s)} из 4`} className="num text-12 text-brand-fg">
        {dotsText(skillLevel(s))}
      </span>
      <Chips className="ml-auto justify-end">
        {s.sources.map((x) => (
          <Tag key={x}>{SOURCE_SHORT[x] ?? x}</Tag>
        ))}
      </Chips>
    </ListRow>
  );
}

/** Топ-10 навыков; «Все навыки» открывает полный список с поиском и фильтром. */
function Skills({ all }: { all: SkillWithTrust[] }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<SkillFilter>("all");
  const ranked = rankSkills(all);
  if (ranked.length === 0) return <p className="text-14 text-muted">{T.noSkills}</p>;
  const shown = open ? filterSkills(ranked, query, filter) : ranked.slice(0, TOP_SKILLS);
  const withEv = shown.filter((s) => s.top_evidence.length > 0);
  return (
    <div className="flex min-w-0 flex-col">
      {open && (
        <div className="flex flex-col gap-2 pb-2 sm:flex-row sm:items-center">
          <Input type="search" aria-label={T.skillSearch} placeholder={T.skillSearch} value={query} onChange={(e) => setQuery(e.target.value)} className="sm:max-w-xs" />
          <SegmentedControl
            label={T.skillFilter}
            value={filter}
            onValueChange={(v) => setFilter(v as SkillFilter)}
            options={[
              { value: "all", label: T.filterAll },
              { value: "confirmed", label: T.filterConfirmed },
              { value: "claimed", label: T.filterClaimed },
            ]}
            className="self-start"
          />
        </div>
      )}
      {shown.length === 0 ? <p className="py-2 text-14 text-muted">{T.nothingFound}</p> : shown.map((s) => <SkillRow key={s.skill.slug} s={s} />)}
      {ranked.length > TOP_SKILLS && (
        <Button variant="outline" className="mt-3 self-start" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? T.hideSkills : T.allSkills(ranked.length)}
        </Button>
      )}
      {withEv.length > 0 && (
        <details className="pt-3 text-14">
          <summary className="cursor-pointer select-none font-semibold">{T.evidence}</summary>
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

const COL_SKILLS = 12;

function ClaimedColumn({
  title,
  hint,
  grade,
  claimedGrade,
  skills,
  empty,
  state,
}: {
  title: string;
  hint: string;
  grade: string | null;
  claimedGrade: boolean;
  skills: SkillWithTrust[];
  empty: string;
  state: "claimed" | "confirmed";
}) {
  return (
    <section aria-label={title} className="flex min-w-0 flex-col gap-2.5 rounded-lg border border-hairline p-3.5">
      <div className="flex items-baseline justify-between gap-2">
        <Lbl>{title}</Lbl>
        <Num className="text-20 font-semibold" aria-label={T.skillsCount(skills.length)}>
          {skills.length}
        </Num>
      </div>
      <p className="text-12 text-muted">{hint}</p>
      <div className="flex items-center gap-2 text-13">
        <span className="text-muted">{T.gradeLbl}</span>
        {grade ? <GradeTag claimed={claimedGrade}>{grade}</GradeTag> : <span className="text-muted">{T.noGrade}</span>}
      </div>
      {skills.length === 0 ? (
        <p className="text-13 text-muted">{empty}</p>
      ) : (
        <Chips>
          {skills.slice(0, COL_SKILLS).map((s) => (
            <SkillTag key={s.skill.slug} name={s.skill.name} state={state} />
          ))}
          {skills.length > COL_SKILLS && <span className="text-13 text-muted">{T.more(skills.length - COL_SKILLS)}</span>}
        </Chips>
      )}
    </section>
  );
}

/** Отдельный блок: слева то, что кандидат заявил, справа то, что подтверждено; у каждой колонки счётчик. */
function ClaimedConfirmed({ row, skills }: { row: ClaimedVsConfirmed | null; skills: SkillWithTrust[] }) {
  const { confirmed, claimed } = splitClaimed(skills);
  const declared = row ? (row.declared_grade ?? row.resume_grade ?? null) : null;
  return (
    <div className="flex flex-col gap-3">
      {row && (
        <p className="text-13 text-muted">
          {T.profession}: <Num className="text-ink">{professionTitle(row.profession)}</Num>
        </p>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <ClaimedColumn title={T.claimedCol} hint={T.claimedColHint} grade={declared ? gradeTitle(declared) : null} claimedGrade skills={claimed} empty={T.noneClaimed} state="claimed" />
        <ClaimedColumn
          title={T.confirmedCol}
          hint={T.confirmedColHint}
          grade={row?.confirmed_grade ? gradeTitle(row.confirmed_grade) : null}
          claimedGrade={false}
          skills={confirmed}
          empty={T.noneConfirmed}
          state="confirmed"
        />
      </div>
    </div>
  );
}

function Body({ c, vacancyId, needId }: { c: CandidateCardFull; vacancyId: string | null; needId: string | null }) {
  const cvc = c.claimed_vs_confirmed ?? [];
  const main = cvc.find((x) => x.confirmed_grade) ?? cvc[0] ?? null;
  const confirmedGrade = main?.confirmed_grade ?? null;
  const gradeLabel = confirmedGrade ? gradeTitle(confirmedGrade) : c.grade ? (GRADE_LABEL[c.grade] ?? c.grade) : null;
  const role = c.primary_role ? roleLabel(c.primary_role) : null;
  const stack = c.primary_stack.slice(0, 2).join(", ");
  const items: WhyItem[] = (c.match?.explanation ?? []).map((i) => ({ kind: WHY_KIND[i.kind], text: i.text }));
  const protocol = fspResults(c.fsp_highlights);
  const experience = dedupeExperience(c.experience);
  const strength = c.strength ? Math.round(c.strength.value * 100) : null;
  const cat = c.categories?.[0] ?? (main?.confirmed_grade ? { profession: main.profession, grade: main.confirmed_grade } : null);
  const cats = useNeedCategoriesNeedsNeedIdCategoriesGet(needId ?? "", { query: { enabled: !!needId } });
  const median =
    cats.data?.status === 200 && cat ? cats.data.data.categories.find((x) => x.profession === cat.profession && x.grade === cat.grade)?.median_salary : null;
  const [shortlisted, setShortlisted] = useState(c.is_shortlisted ?? false);
  const [shortlistError, setShortlistError] = useState(false);
  const add = useShortlistAddNeedsNeedIdShortlistPseudoIdPost();
  const remove = useShortlistRemoveNeedsNeedIdShortlistPseudoIdDelete();
  const toggleShortlist = () => {
    if (!needId) return;
    const on = !shortlisted;
    setShortlistError(false);
    setShortlisted(on);
    (on ? add : remove).mutate(
      { needId, pseudoId: c.pseudo_id },
      {
        onError: () => {
          setShortlisted(!on);
          setShortlistError(true);
        },
      },
    );
  };
  const offered = c.offers_from_you.length > 0;
  const [offerOpen, setOfferOpen] = useState(false);
  const [interestOpen, setInterestOpen] = useState(false);
  const dialogCandidate = { pseudoId: c.pseudo_id, pseudonym: c.pseudonym, salaryMin: c.salary_min ?? null };
  const where = [c.city, c.relocation ? "готов к релокации" : null, c.formats.map((f) => FORMAT_LABEL[f] ?? f).join(" или ").toLowerCase()].filter(Boolean);
  const hasMarket = !!c.salary_min || !!median;
  return (
    <div className="flex flex-col gap-4">
      <Panel aria-label={T.header} className="flex flex-wrap items-center gap-4">
        {c.avatar_url ? <Avatar name={c.full_name ?? c.pseudonym} src={avatarSrc(c.avatar_url)} size={72} /> : <ConstellationAvatar seed={c.avatar_seed} size={72} />}
        <div className="flex min-w-[200px] flex-1 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2.5">
            <H1 className="break-words text-[28px]">{displayPseudonym(c.pseudonym, c.primary_role)}</H1>
            {gradeLabel && <GradeTag claimed={!confirmedGrade}>{[gradeLabel, role, stack].filter(Boolean).join(" · ")}</GradeTag>}
            {protocol.length > 0 && <StatusTag state="ok">{T.fspVerified}</StatusTag>}
            {c.interested_you && <StatusTag state="confirmed">{IT.interestedYou}</StatusTag>}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-13 text-muted">
            {c.full_name && <span className="text-ink">{c.full_name}</span>}
            {where.map((w) => (
              <span key={w}>{w}</span>
            ))}
            <span>{SEARCH_STATUS_LABEL[c.search_status]}</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {strength !== null && (
            <div className="flex items-center gap-3">
              <MatchRingV2 value={strength} size={64} />
              <div className="flex flex-col gap-0.5">
                <Lbl>{T.strength}</Lbl>
                {c.strength?.rank != null && <Num className="text-14">{T.rank(c.strength.rank)}</Num>}
              </div>
            </div>
          )}
          {c.match && (
            <div className="flex items-center gap-3">
              <MatchRingV2 value={Math.round(c.match.score * 100)} size={64} />
              <Lbl>{T.match}</Lbl>
            </div>
          )}
        </div>
      </Panel>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {(c.skills.length > 0 || main) && (
            <Panel aria-label={T.claimedConfirmed}>
              <PanelCap title={<Gloss k="claimed"><H2>{T.claimedConfirmed}</H2></Gloss>} />
              <ClaimedConfirmed row={main} skills={c.skills} />
            </Panel>
          )}
          <Panel aria-label={T.skills}>
            <PanelCap title={<Gloss k="trust"><H2>{T.skills}</H2></Gloss>} aside={<Lbl>{T.skillsHint}</Lbl>} />
            <Skills all={c.skills} />
          </Panel>
          {protocol.length > 0 && (
            <Panel aria-label={T.fsp}>
              <PanelCap title={T.fsp} aside={<Lbl>{T.fspHint}</Lbl>} />
              <FspProtocol results={protocol} />
            </Panel>
          )}
          <Panel aria-label={T.experience}>
            <PanelCap
              title={<Lbl>{T.experience}</Lbl>}
              aside={experience.length === 0 ? <StatusTag state="claimed">{T.experienceHidden}</StatusTag> : <Lbl>{T.experienceHint}</Lbl>}
            />
            {experience.length > 0 && (
              <ul className="flex flex-col gap-2 text-14">
                {experience.map((e, n) => (
                  <li key={n} className="flex flex-col">
                    <b className="font-semibold">{e.title ?? "Роль не указана"}</b>
                    {e.skills.length > 0 && <span className="text-13 text-muted">{e.skills.join(", ")}</span>}
                    <Num className="text-12 text-muted">{yearsLabel(e.months)}</Num>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <aside className="flex min-w-0 flex-col gap-4">
          <Panel aria-label={T.interestPanel} className="flex flex-col gap-3 border-brand">
            <Lbl>{T.interestPanel}</Lbl>
            {offered && (
              <div className="flex flex-wrap items-center gap-2">
                {c.offers_from_you.map((o, i) => (
                  <StatusTag key={i} state="claimed">
                    {OFFER_STATUS_LABEL[String(o.status)] ?? String(o.status ?? "")}
                  </StatusTag>
                ))}
              </div>
            )}
            <Button size="lg" className="w-full" onClick={() => setOfferOpen(true)}>
              {T.invite}
            </Button>
            <Button variant="outline" className="w-full" onClick={() => setInterestOpen(true)}>
              {T.interest}
            </Button>
            <OfferDialog open={interestOpen} onOpenChange={setInterestOpen} mode="interest" candidate={dialogCandidate} vacancyId={vacancyId ?? ""} />
            <OfferDialog open={offerOpen} onOpenChange={setOfferOpen} candidate={dialogCandidate} vacancyId={vacancyId ?? ""} alreadyOffered={offered} />
            {needId && (
              <Button variant="outline" className="w-full" aria-pressed={shortlisted} onClick={toggleShortlist}>
                {shortlisted ? `✓ ${T.shortlisted}` : T.shortlist}
              </Button>
            )}
            {shortlistError && (
              <p role="alert" className="text-12 text-error">
                {T.shortlistError}
              </p>
            )}
            <p className="text-12 text-muted">{T.contacts}</p>
          </Panel>
          {items.length > 0 && (
            <Panel aria-label={T.why}>
              <PanelCap title={T.why} />
              <MatchWhy items={items} />
            </Panel>
          )}
        </aside>
      </div>
      {hasMarket && (
        <Panel aria-label={T.market} className="flex flex-col gap-2">
          <Lbl>{T.market}</Lbl>
          {c.salary_min && (
            <ListRow className="py-1.5">
              <span className="text-muted">{T.candidateWants}</span>
              <Num className="ml-auto">от {formatRub(c.salary_min)}</Num>
            </ListRow>
          )}
          {median ? (
            <ListRow className="py-1.5">
              <span className="text-muted">{T.median}</span>
              <Num className="ml-auto">{formatRub(median)}</Num>
            </ListRow>
          ) : null}
        </Panel>
      )}
    </div>
  );
}

/** Карточка кандидата для работодателя (тёмная, макет v2): анонимный DTO, пишет просмотр. */
export default function CandidateView() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const vacancyId = params.get("vacancy");
  const needId = params.get("need_id");
  const source = (["search", "match", "similar", "direct"] as const).find((s) => s === params.get("source")) ?? "direct";
  const q = useCandidateCardCandidatesPseudoIdCardGet(id, { vacancy_id: vacancyId ?? undefined, source }, { query: { retry: false } });
  const back = vacancyId ? `/employer/vacancies/${vacancyId}/shortlist` : "/employer";
  const card = q.data?.status === 200 ? q.data.data : null;
  const cat = card?.categories?.[0] ?? null;
  const catHref = cat ? `/employer/categories/${cat.profession}/${cat.grade}${needId ? `?need_id=${encodeURIComponent(needId)}` : ""}` : back;
  const err = q.error instanceof ApiError ? q.error : null;
  const hidden = q.isError && (err?.status === 404 || err?.status === 403);
  return (
    <div className="min-h-[calc(100dvh-4rem)]">
      <main className={PAGE.normal}>
        <nav aria-label={T.nav} className="flex flex-wrap items-center gap-1.5 text-13">
          <Link to={back} className="font-semibold text-brand-fg hover:underline">
            {T.crumbRoot}
          </Link>
          {cat && (
            <>
              <span className="text-muted">›</span>
              <Link to={catHref} className="font-semibold text-brand-fg hover:underline">
                {professionTitle(cat.profession)} · {gradeTitle(cat.grade)}
              </Link>
            </>
          )}
          {card && (
            <>
              <span className="text-muted">›</span>
              <span className="text-muted">{displayPseudonym(card.pseudonym, card.primary_role)}</span>
            </>
          )}
        </nav>
        {q.isPending && <Skeletons />}
        {hidden && (
          <EmptyState
            title={T.hidden}
            action={
              <Link to={catHref} className={buttonVariants({ size: "lg" })}>
                {cat ? T.toCategory : T.back}
              </Link>
            }
          />
        )}
        {q.isError && !hidden && <ErrorState title={T.failed} code={err ? `ошибка ${err.status}` : undefined} onRetry={() => void q.refetch()} />}
        {card && <Body c={card} vacancyId={vacancyId} needId={needId} />}
      </main>
    </div>
  );
}
