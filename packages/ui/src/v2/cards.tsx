import type { FormEvent, ReactNode } from "react";

import { cn } from "../lib/cn";
import { cardInteractive } from "../primitives/display";
import { Button } from "../primitives/button";
import { CheckItem, Chips, CompanyMark, GradeTag, Lbl, MeterBar, SkillTag, StatusTag, clamp } from "./primitives";

/* Карточки и лента v2: категория, кандидат, событие, строка запроса, приглашение. Данные и колбэки — снаружи. */

/* ---------- MatchRing v2 (кольцо 44 px в карточке кандидата) ---------- */
/** Кольцо совпадения v2: число в центре, дуга brand. `className` может задать размер (`md:size-13`). */
export function MatchRingV2({ value, size = 44, className }: { value: number; size?: number; className?: string }) {
  const v = Math.round(clamp(value));
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Совпадение ${v} %`} className={cn("block flex-none", className)}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--tint-100)" strokeWidth="4" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--brand)"
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={`${(c * v) / 100} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x={size / 2}
        y={size / 2 + Math.round(size / 11)}
        textAnchor="middle"
        fontFamily="JetBrains Mono, monospace"
        fontSize={Math.round(size * 0.3)}
        fontWeight="700"
        fill="var(--ink)"
      >
        {v}
      </text>
    </svg>
  );
}

/* ---------- CategoryCard ---------- */

export interface CategoryCardData {
  /** «Backend · Middle». */
  title: string;
  /** Гистограмма ожиданий по корзинам. */
  histogram: number[];
  /** Индекс корзины, выделенной цветом (например, медиана или вилка работодателя). */
  highlight?: number;
  /** Три числа под гистограммой: «37 человек», «220 000 медиана ₽», «24 % с ФСП». */
  stats: { value: ReactNode; label: string }[];
}

/** Карточка категории `.cat`: заголовок, гистограмма ожиданий, три метрики. Кликабельна целиком. */
export function CategoryCard({
  c,
  selected,
  href,
  onClick,
  className,
}: {
  c: CategoryCardData;
  selected?: boolean;
  href?: string;
  onClick?: () => void;
  className?: string;
}) {
  const max = Math.max(1, ...c.histogram);
  const n = c.histogram.length || 1;
  const w = 150 / n;
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <b className="font-mono text-16 leading-[1.3] font-semibold">{c.title}</b>
        <span aria-hidden className="num text-muted">
          ›
        </span>
      </div>
      <svg width="100%" height="34" viewBox="0 0 150 34" preserveAspectRatio="none" role="img" aria-label="Распределение ожиданий по зарплате">
        {c.histogram.map((v, i) => {
          const h = (v / max) * 34;
          return <rect key={i} x={i * w + 1} y={34 - h} width={Math.max(0, w - 2)} height={h} rx="1.5" fill={i === c.highlight ? "var(--brand)" : "var(--tint-200)"} />;
        })}
      </svg>
      <div className="grid grid-cols-3 gap-2">
        {c.stats.slice(0, 3).map((s) => (
          <div key={s.label}>
            <b className="block font-mono text-14 leading-[1.2] font-semibold">{s.value}</b>
            <span className="font-mono text-11 font-medium text-muted">{s.label}</span>
          </div>
        ))}
      </div>
    </>
  );
  const cls = cn(
    "flex flex-col gap-2.5 rounded-xl border border-hairline bg-card p-3.5 text-left text-ink no-underline",
    (href || onClick) && cardInteractive,
    selected && "border-brand shadow-[0_0_0_1px_var(--brand)]",
    className,
  );
  if (href)
    return (
      <a href={href} onClick={onClick} aria-current={selected ? "true" : undefined} className={cls}>
        {body}
      </a>
    );
  if (onClick)
    return (
      <button type="button" onClick={onClick} aria-pressed={selected} className={cn(cls, "w-full")}>
        {body}
      </button>
    );
  return <div className={cls}>{body}</div>;
}

/* ---------- CandidateCard v2 ---------- */

export interface CandidateCardV2Data {
  /** «Backend #3377». */
  pseudonym: string;
  match: number;
  grade: string;
  /** Грейд подтверждён тестом; иначе — заявлен (пунктир). */
  confirmed: boolean;
  /** «190–220 тыс. ₽». */
  salary?: string;
  skills: { name: string; level?: number; claimed?: boolean }[];
  /** «Удалённо · 3 навыка подтверждены». */
  meta?: string;
}

/**
 * Анонимная карточка кандидата v2: кольцо совпадения, псевдоним, грейд, вилка, навыки, одно действие.
 * `wide` — с 768 px строкой, как в «Лучших совпадениях» (кольцо · данные · вилка и действие справа);
 * на телефоне — столбиком, как без него.
 */
export function CandidateCardV2({
  c,
  action,
  onOpen,
  openLabel = "Открыть профиль",
  wide,
  className,
}: {
  c: CandidateCardV2Data;
  /** Своё действие вместо «Открыть профиль» (ссылка роутера и т. п.). */
  action?: ReactNode;
  onOpen?: () => void;
  openLabel?: string;
  wide?: boolean;
  className?: string;
}) {
  const act =
    action ??
    (onOpen && (
      <Button variant="outline" className="h-9 sm:h-9" onClick={onOpen}>
        {openLabel}
      </Button>
    ));
  const tags = (
    <div className="flex items-center gap-1.5">
      <GradeTag claimed={!c.confirmed}>{c.grade}</GradeTag>
      <StatusTag state={c.confirmed ? "confirmed" : "claimed"}>{c.confirmed ? "подтверждён" : "заявлен"}</StatusTag>
    </div>
  );
  const skills = c.skills.length > 0 && (
    <Chips>
      {c.skills.map((s) => (
        <SkillTag key={s.name} name={s.name} level={s.level} state={s.claimed ? "claimed" : "confirmed"} />
      ))}
    </Chips>
  );
  if (wide)
    return (
      <article
        aria-label={c.pseudonym}
        className={cn(
          "grid min-w-0 grid-cols-[44px_minmax(0,1fr)] items-center gap-3 rounded-xl border border-hairline bg-card p-4 md:grid-cols-[52px_minmax(0,1fr)_auto] md:gap-x-4 md:gap-y-2",
          className,
        )}
      >
        <MatchRingV2 value={c.match} className="md:row-span-3 md:size-13" />
        <div className="flex min-w-0 flex-col gap-1.5 md:flex-row md:flex-wrap md:items-center md:gap-2">
          <b className="truncate font-mono text-[15px] font-semibold">{c.pseudonym}</b>
          {tags}
        </div>
        {c.salary && <div className="num col-span-2 text-[22px] leading-[1.1] md:col-span-1 md:col-start-3 md:row-start-1 md:text-right md:text-20">{c.salary}</div>}
        {skills && <div className="col-span-2 md:col-span-1 md:col-start-2">{skills}</div>}
        {c.meta && <div className="col-span-2 text-13 text-muted md:col-span-1 md:col-start-2">{c.meta}</div>}
        {act && <div className="col-span-2 grid md:col-span-1 md:col-start-3 md:row-span-2 md:row-start-2 md:self-end md:justify-items-end">{act}</div>}
      </article>
    );
  return (
    <article aria-label={c.pseudonym} className={cn("flex min-w-0 flex-col gap-3 rounded-xl border border-hairline bg-card p-4", className)}>
      <div className="flex items-center gap-3">
        <MatchRingV2 value={c.match} />
        <div className="flex min-w-0 flex-col gap-1.5">
          <b className="truncate font-mono text-[15px] font-semibold">{c.pseudonym}</b>
          {tags}
        </div>
      </div>
      {c.salary && <div className="num text-[22px] leading-[1.1]">{c.salary}</div>}
      {skills}
      {c.meta && <div className="text-13 text-muted">{c.meta}</div>}
      {act}
    </article>
  );
}

/* ---------- RankedCandidateCard (страница категории) ---------- */

export interface RankedCandidateData {
  pseudonym: string;
  match: number;
  grade: string;
  /** Грейд подтверждён тестом; иначе карточка пунктирная («не подтверждён»). */
  confirmed: boolean;
  /** Сила профиля 0–100 и подпись справа от полосы («сила 71 · № 1»). Нет — полосы нет. */
  strength?: { value: number; label: string };
  /** «190–220 тыс. ₽». */
  salary?: string;
  /** «Москва · удалёнка». */
  place?: string;
  skills: { name: string; level?: number; claimed?: boolean }[];
  /** Достижение ФСП одной строкой. */
  fsp?: string;
  /** До трёх фактов «почему»; `warn` — с восклицанием. */
  reasons: { text: string; warn?: boolean }[];
  /** Подпись под грейдом неподтверждённого («грейд заявлен»). */
  note?: string;
  /** Метка «интересовался вами». */
  interestedYou?: boolean;
}

/**
 * Строка категории v2: слева кольцо, псевдоним, грейд и сила; затем вилка, навыки и ФСП; факты «почему»;
 * справа действия. С 768 px — четыре колонки, на телефоне — столбиком. Неподтверждённые — пунктиром.
 */
export function RankedCandidateCard({
  c,
  actions,
  onOpen,
  openLabel,
  className,
}: {
  c: RankedCandidateData;
  actions?: ReactNode;
  onOpen?: () => void;
  openLabel?: string;
  className?: string;
}) {
  const name = (
    <b className="truncate font-mono text-[15px] font-semibold">{c.pseudonym}</b>
  );
  return (
    <article
      aria-label={c.pseudonym}
      data-confirmed={c.confirmed}
      className={cn(
        "grid min-w-0 gap-3 rounded-xl border bg-card p-4 md:grid-cols-[1.35fr_1.1fr_1.5fr_150px] md:items-center md:gap-5",
        c.confirmed ? "border-hairline" : "border-dashed border-hairline",
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex items-center gap-3">
          <MatchRingV2 value={c.match} />
          <div className="flex min-w-0 flex-col gap-1.5">
            <div className="flex flex-wrap items-center gap-2">
              {onOpen ? (
                <button type="button" onClick={onOpen} aria-label={openLabel ?? `Открыть профиль ${c.pseudonym}`} className="min-w-0 text-left hover:underline">
                  {name}
                </button>
              ) : (
                name
              )}
              <GradeTag claimed={!c.confirmed}>{c.grade}</GradeTag>
              <StatusTag state={c.confirmed ? "confirmed" : "claimed"}>{c.confirmed ? "подтверждён" : "не подтверждён"}</StatusTag>
            </div>
            {c.strength ? (
              <div className="flex min-w-[120px] flex-col gap-1">
                <MeterBar value={c.strength.value} label="Сила профиля" className="w-[120px]" />
                <span className="num text-11 text-muted">{c.strength.label}</span>
              </div>
            ) : (
              c.note && <Lbl>{c.note}</Lbl>
            )}
          </div>
        </div>
        {c.interestedYou && (
          <StatusTag state="confirmed" className="self-start">
            интересовался вами
          </StatusTag>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-2.5 overflow-hidden">
        {c.skills.length > 0 && (
          <Chips>
            {c.skills.map((s) => (
              <SkillTag key={s.name} name={s.name} level={s.level} state={s.claimed ? "claimed" : "confirmed"} />
            ))}
          </Chips>
        )}
        {c.fsp && <CheckItem>{c.fsp}</CheckItem>}
        {(c.salary || c.place) && (
          <div className="flex flex-col gap-0.5">
            {c.salary && <span className="num text-xl leading-[1.1]">{c.salary}</span>}
            {c.place && <span className="text-12 text-muted">{c.place}</span>}
          </div>
        )}
      </div>
      <div className="flex min-w-0 flex-col gap-1.5">
        {c.reasons.map((r) => (
          <CheckItem key={r.text} warn={r.warn}>
            {r.text}
          </CheckItem>
        ))}
      </div>
      {actions && <div className="flex flex-col gap-2">{actions}</div>}
    </article>
  );
}

/** Переключатель-фильтр `.sk`: нажатый — сплошной brand, ненажатый — серый. */
export function FilterChip({
  pressed,
  onToggle,
  children,
  className,
}: {
  pressed: boolean;
  onToggle: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onToggle}
      className={cn(
        "inline-flex min-h-9 items-center gap-1.5 rounded-sm border px-2.5 py-[5px] font-mono text-12 leading-none font-medium whitespace-nowrap",
        pressed ? "border-brand bg-tint-50 text-chip-fg" : "border-hairline bg-card text-muted hover:border-brand",
        className,
      )}
    >
      {children}
      {pressed && <span aria-hidden>✓</span>}
    </button>
  );
}

/* ---------- FeedEvent ---------- */

/** Событие ленты `.ev`: время слева, текст справа. Оборачивать в `FeedList`. */
export function FeedEvent({ time, children, className }: { time: string; children: ReactNode; className?: string }) {
  return (
    <li className={cn("flex items-start gap-2.5 border-t border-hairline py-[9px] text-13 leading-[1.4] first:border-t-0 first:pt-0", className)}>
      <time className="w-[38px] flex-none font-mono text-11 leading-[1.6] font-medium text-muted">{time}</time>
      <span className="min-w-0">{children}</span>
    </li>
  );
}

export function FeedList({ label = "Лента событий", className, children }: { label?: string; className?: string; children: ReactNode }) {
  return (
    <ul aria-label={label} className={cn("m-0 list-none p-0", className)}>
      {children}
    </ul>
  );
}

/* ---------- QueryBar ---------- */

/** Строка запроса работодателя `.q`: поле и «Подобрать». Enter отправляет. */
export function QueryBar({
  value,
  onChange,
  onSubmit,
  placeholder = "Кого вы ищете: роль, грейд, навыки, вилка",
  label = "Кого вы ищете",
  submitLabel = "Подобрать",
  loading,
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (v: string) => void;
  placeholder?: string;
  label?: string;
  submitLabel?: string;
  loading?: boolean;
  className?: string;
}) {
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onSubmit(value.trim());
  };
  return (
    <form
      role="search"
      onSubmit={submit}
      className={cn("flex min-h-[52px] items-center gap-2.5 rounded-xl border border-brand bg-card py-1.5 pr-1.5 pl-3.5", className)}
    >
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className="min-w-0 flex-1 border-0 bg-transparent text-[15px] text-ink outline-none placeholder:text-muted"
      />
      <Button type="submit" className="h-10 sm:h-10" loading={loading}>
        {submitLabel}
      </Button>
    </form>
  );
}

/* ---------- OfferCard v2 ---------- */

export interface OfferCardV2Data {
  company: string;
  /** «4.6 / 5». */
  rating?: string;
  /** Компания проверена модерацией. */
  verified?: boolean;
  /** «отвечает в 85 % · 18 ч». */
  responseNote?: string;
  /** Название вакансии или приглашения без вакансии. */
  title?: string;
  /** «150–220 тыс. ₽». */
  salary: string;
  /** «до НДФЛ» или «на руки». */
  salaryNote?: string;
  /** «мини-задание · 45 мин · до 12.10». */
  task?: string;
  /** «Почему ты»: 1–3 строки. */
  reasons?: string[];
  /** «срок до 14.10». */
  deadline?: string;
}

/**
 * Приглашение или интерес для кандидата v2: компания, вилка, «почему ты», действия.
 * `compact` — только компания и вилка (строка списка). `dimmed` — неактивное (просрочено, отклонено).
 */
export function OfferCardV2({
  o,
  actions,
  compact,
  dimmed,
  className,
}: {
  o: OfferCardV2Data;
  actions?: ReactNode;
  compact?: boolean;
  dimmed?: boolean;
  className?: string;
}) {
  const head = (
    <div className="flex min-w-0 items-center gap-2.5">
      <CompanyMark name={o.company} />
      <div className="flex min-w-0 flex-col gap-1">
        <b className="font-semibold">{o.company}</b>
        {compact ? (
          <span className="num text-12">
            {o.salary}
            {o.salaryNote && ` · ${o.salaryNote}`}
          </span>
        ) : (
          (o.rating || o.verified) && (
            <div className="flex flex-wrap items-center gap-1.5">
              {o.rating && <span className="num text-12">{o.rating}</span>}
              {o.verified && <StatusTag state="ok">проверена</StatusTag>}
            </div>
          )
        )}
        {!compact && o.responseNote && <span className="num text-11 text-muted">{o.responseNote}</span>}
      </div>
    </div>
  );
  if (compact)
    return (
      <article aria-label={o.company} className={cn("rounded-xl border border-hairline bg-card p-4", dimmed && "opacity-60", className)}>
        {head}
      </article>
    );
  // Без действий и срока (лента «Вами интересуются» на Главной) — три колонки, как в макете v2_me__after.
  const side = Boolean(actions || o.deadline);
  return (
    <article
      aria-label={o.company}
      className={cn(
        "grid min-w-0 items-center gap-4 rounded-xl border border-hairline bg-card p-4 md:gap-5",
        side ? "md:grid-cols-[1.1fr_.9fr_1.5fr_190px]" : "md:grid-cols-[1.1fr_1fr_1.6fr]",
        dimmed && "opacity-60",
        className,
      )}
    >
      {head}
      <div className="flex flex-col gap-1.5">
        {o.title && <span className="break-words text-13 text-muted">{o.title}</span>}
        <div className="flex flex-col gap-0.5">
          <span className="num text-[22px] leading-[1.1]">{o.salary}</span>
          {o.salaryNote && <Lbl>{o.salaryNote}</Lbl>}
        </div>
        {o.task && (
          <div className="flex flex-wrap items-center gap-2">
            <StatusTag>задание</StatusTag>
            <span className="num text-12">{o.task}</span>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-1.5">
        {(o.reasons ?? []).map((r) => (
          <CheckItem key={r}>{r}</CheckItem>
        ))}
      </div>
      {side && (
        <div className="flex flex-col items-stretch gap-1.5">
          {o.deadline && <span className="num text-12 text-muted">{o.deadline}</span>}
          {actions}
        </div>
      )}
    </article>
  );
}
