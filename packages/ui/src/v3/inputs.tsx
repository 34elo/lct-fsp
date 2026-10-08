import { Minus, Plus } from "lucide-react";
import { useEffect, useMemo, useState, type InputHTMLAttributes } from "react";

import { cn } from "../lib/cn";
import { Slider, useFieldProps } from "../primitives/form";
import { Combobox, ValueChip, type ComboOption } from "./combobox";

/* ---------- SkillInput ---------- */

/** Навык в поле: `value` — slug из справочника или введённое имя; `isNew` — нет в справочнике. */
export interface SkillValue {
  value: string;
  label: string;
  isNew?: boolean;
}

/** Подсказка навыка от источника (E39-3: `/taxonomy/skills/suggest`; до него — справочник на клиенте). */
export interface SkillSuggestion {
  slug: string;
  name: string;
  hint?: string;
}

export type SkillSource = (query: string, signal: AbortSignal) => Promise<SkillSuggestion[]>;

/**
 * Ввод навыков: асинхронные подсказки, чипсы, своё значение помечено «новый».
 * Источник подсказок — пропс `suggest`, чтобы экран мог подменить справочник на API без правки компонента.
 */
export function SkillInput({
  value,
  onChange,
  suggest,
  allowNew = true,
  max,
  placeholder = "Навык: Python, SQL…",
  disabled,
  id,
  className,
  "aria-label": ariaLabel = "Навыки",
  "data-testid": testId,
  debounceMs,
}: {
  debounceMs?: number;
  value: SkillValue[];
  onChange: (v: SkillValue[]) => void;
  suggest: SkillSource;
  allowNew?: boolean;
  max?: number;
  placeholder?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
  "data-testid"?: string;
}) {
  const load = useMemo(
    () => async (q: string, signal: AbortSignal) =>
      (await suggest(q, signal)).map<ComboOption>((s) => ({ value: s.slug, label: s.name, hint: s.hint })),
    [suggest],
  );
  return (
    <Combobox
      multiple
      value={value.map((v) => v.value)}
      selectedOptions={value}
      onChange={(_, opts) => onChange(opts.map((o) => ({ value: o.value, label: o.label, isNew: o.isNew || undefined })))}
      loadOptions={load}
      debounceMs={debounceMs}
      creatable={allowNew}
      createLabel={(q) => `Добавить «${q}» — новый навык`}
      max={max}
      placeholder={placeholder}
      emptyText={allowNew ? "Начните вводить навык" : "Нет такого навыка"}
      disabled={disabled}
      id={id}
      className={className}
      aria-label={ariaLabel}
      data-testid={testId}
    />
  );
}

/** Подсказки из готового списка навыков (пока нет API E39-3): поиск по имени и slug, до `limit` штук. */
export function localSkillSource(skills: SkillSuggestion[], limit = 20): SkillSource {
  return async (q) => {
    const n = q.trim().toLocaleLowerCase("ru");
    const hits = n ? skills.filter((s) => s.name.toLocaleLowerCase("ru").includes(n) || s.slug.includes(n)) : skills;
    // Сначала — начинающиеся с запроса.
    return [...hits].sort((a, b) => Number(!a.name.toLocaleLowerCase("ru").startsWith(n)) - Number(!b.name.toLocaleLowerCase("ru").startsWith(n))).slice(0, limit);
  };
}

/** Только для чтения: чипсы навыков в том же виде, что и в поле. */
export function SkillChipsView({ value, className }: { value: SkillValue[]; className?: string }) {
  return (
    <span className={cn("flex flex-wrap gap-1.5", className)}>
      {value.map((v) => (
        <ValueChip key={v.value} option={v} />
      ))}
    </span>
  );
}

/* ---------- ProfessionInput ---------- */

export interface ProfessionOption {
  slug: string;
  title: string;
}

/** Выбор профессии из справочника: поиск по названию, клавиатура как у `Select`. */
export function ProfessionInput({
  value,
  onChange,
  professions,
  placeholder = "Профессия",
  clearable,
  disabled,
  id,
  className,
  "aria-label": ariaLabel = "Профессия",
  "data-testid": testId,
}: {
  value: string | null;
  onChange: (slug: string | null) => void;
  professions: ProfessionOption[];
  placeholder?: string;
  clearable?: boolean;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
  "data-testid"?: string;
}) {
  const options = useMemo(() => professions.map((p) => ({ value: p.slug, label: p.title })), [professions]);
  return (
    <Combobox
      value={value}
      onChange={(v) => onChange(v)}
      options={options}
      searchable={options.length >= 8}
      clearable={clearable}
      placeholder={placeholder}
      disabled={disabled}
      id={id}
      className={className}
      aria-label={ariaLabel}
      data-testid={testId}
    />
  );
}

/* ---------- NumberInput ---------- */

const NBSP = " ";
/** «1234567» → «1 234 567» (неразрывные пробелы). */
export function groupDigits(n: number): string {
  return Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}
/** Разбор ввода: только цифры (и минус, если `negative`). Пусто → null. */
export function parseDigits(s: string, negative = false): number | null {
  const neg = negative && s.trim().startsWith("-");
  const d = s.replace(/\D/g, "");
  if (!d) return null;
  const n = Number(d);
  return neg ? -n : n;
}
const clampN = (n: number, min?: number, max?: number) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, n));

type NumberBase = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "type" | "min" | "max" | "step" | "size">;

/** Целое число без стрелок браузера: текстовое поле с `inputMode=numeric`, кнопки − / +, ↑ ↓ — шаг. */
export function NumberInput({
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
  grouped,
  stepper = true,
  className,
  disabled,
  onBlur,
  ...p
}: NumberBase & {
  value: number | null;
  onChange: (v: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  /** Разряды пробелами (деньги, большие числа). */
  grouped?: boolean;
  /** Кнопки − / +. */
  stepper?: boolean;
}) {
  const field = useFieldProps();
  const fmt = (v: number | null) => (v == null ? "" : grouped ? groupDigits(v) : String(v));
  const [draft, setDraft] = useState(fmt(value));
  // Внешнее значение поменялось — показываем его (не трогая ввод, если он равен значению).
  useEffect(() => {
    setDraft((d) => (parseDigits(d, (min ?? 0) < 0) === value ? d : fmt(value)));
    // fmt зависит только от grouped
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, grouped, min]);
  const bump = (dir: 1 | -1) => {
    const next = clampN((value ?? min ?? 0) + dir * step, min, max);
    onChange(next);
    setDraft(fmt(next));
  };
  const btn =
    "inline-flex size-9 shrink-0 items-center justify-center rounded-md text-muted hover:bg-tint-50 hover:text-ink disabled:pointer-events-none disabled:opacity-40";
  return (
    <span
      className={cn(
        "flex h-11 w-full items-center gap-1 rounded-lg border border-hairline bg-card px-1 text-14 text-ink hover:border-brand-mid focus-within:border-brand focus-within:outline-2 focus-within:outline-brand focus-within:-outline-offset-1 has-[input[aria-invalid=true]]:border-error has-[input:disabled]:bg-tint-50",
        !stepper && "px-3",
        className,
      )}
    >
      {stepper && (
        <button type="button" tabIndex={-1} aria-label="Меньше" className={btn} disabled={disabled || (min !== undefined && value !== null && value <= min)} onClick={() => bump(-1)}>
          <Minus className="size-4" aria-hidden />
        </button>
      )}
      <input
        {...field}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        disabled={disabled}
        value={draft}
        onChange={(e) => {
          const n = parseDigits(e.target.value, (min ?? 0) < 0);
          setDraft(n == null ? (e.target.value.trim() === "-" ? "-" : "") : grouped ? groupDigits(n) : String(n));
          onChange(n);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowUp" || e.key === "ArrowDown") {
            e.preventDefault();
            bump(e.key === "ArrowUp" ? 1 : -1);
          }
        }}
        onBlur={(e) => {
          if (value != null) {
            const c = clampN(value, min, max);
            if (c !== value) onChange(c);
            setDraft(fmt(c));
          }
          onBlur?.(e);
        }}
        className={cn("num h-full min-w-0 flex-1 bg-transparent font-medium outline-none placeholder:font-normal placeholder:text-muted", stepper && "text-center")}
        {...p}
      />
      {suffix && <span className="shrink-0 pr-2 font-mono text-13 text-muted">{suffix}</span>}
      {stepper && (
        <button type="button" tabIndex={-1} aria-label="Больше" className={btn} disabled={disabled || (max !== undefined && value !== null && value >= max)} onClick={() => bump(1)}>
          <Plus className="size-4" aria-hidden />
        </button>
      )}
    </span>
  );
}

/* ---------- SalaryRangeInput ---------- */

export interface SalaryRangeValue {
  from: number | null;
  to: number | null;
}

/** Вилка «от — до» в ₽/мес: два поля с разрядами и `₽`, ползунок под ними, без стрелок браузера. */
export function SalaryRangeInput({
  value,
  onChange,
  min = 0,
  max = 1_000_000,
  step = 5_000,
  slider = true,
  disabled,
  invalid,
  fromLabel = "От",
  toLabel = "До",
  fromTestId,
  toTestId,
  className,
}: {
  value: SalaryRangeValue;
  onChange: (v: SalaryRangeValue) => void;
  min?: number;
  max?: number;
  step?: number;
  slider?: boolean;
  disabled?: boolean;
  invalid?: boolean;
  fromLabel?: string;
  toLabel?: string;
  fromTestId?: string;
  toTestId?: string;
  className?: string;
}) {
  const bad = invalid ?? (value.from != null && value.to != null && value.from > value.to);
  const lo = clampN(value.from ?? min, min, max);
  const hi = clampN(value.to ?? max, min, max);
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="grid grid-cols-2 gap-3">
        <label className="flex flex-col gap-1">
          <span className="lbl text-muted">{fromLabel}</span>
          <NumberInput
            value={value.from}
            onChange={(from) => onChange({ ...value, from })}
            min={0}
            grouped
            stepper={false}
            suffix="₽"
            disabled={disabled}
            aria-invalid={bad || undefined}
            aria-label={`${fromLabel}, ₽ в месяц`}
            data-testid={fromTestId}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="lbl text-muted">{toLabel}</span>
          <NumberInput
            value={value.to}
            onChange={(to) => onChange({ ...value, to })}
            min={0}
            grouped
            stepper={false}
            suffix="₽"
            disabled={disabled}
            aria-invalid={bad || undefined}
            aria-label={`${toLabel}, ₽ в месяц`}
            data-testid={toTestId}
          />
        </label>
      </div>
      {slider && (
        <Slider
          min={min}
          max={max}
          step={step}
          minStepsBetweenThumbs={0}
          disabled={disabled}
          value={[Math.min(lo, hi), Math.max(lo, hi)]}
          onValueChange={([a, b]) => onChange({ from: a ?? null, to: b === max && value.to == null ? null : (b ?? null) })}
          aria-label="Вилка"
        />
      )}
    </div>
  );
}
