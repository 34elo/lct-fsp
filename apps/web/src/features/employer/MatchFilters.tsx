import { useEffect, useId, useState, type ReactNode } from "react";

import { Checkbox, ChevronDown, Combobox, ProfessionInput, SalaryRangeInput, SegmentedControl, SkillInput, cn, type ProfessionOption, type SkillSource } from "@fsp/ui";

import { GRADE_LABEL } from "@/features/profile/text";
import { Gi } from "@/shared/Gloss";
import { suggestProfessions } from "@/shared/lib/skills";
import { FORMATS, TEST_GRADES, filterCount, gradeSpan, type Criteria } from "./query-model";
import { FORMAT_LABEL, FIND_TEXT as T } from "./text";

const TRUST_OPTIONS = [
  { value: "any", label: T.trustAny },
  ...[1, 2, 3, 4].map((n) => ({
    value: String(n),
    label: (
      <span>
        <span aria-hidden className="tracking-[.12em]">
          {"●".repeat(n) + "○".repeat(4 - n)}
        </span>
        <span className="sr-only">{`от ${n} из 4`}</span>
      </span>
    ),
  })),
];

/** Крупные города для подсказки; свой город можно ввести. */
const CITIES = ["Москва", "Санкт-Петербург", "Новосибирск", "Екатеринбург", "Казань", "Нижний Новгород", "Краснодар", "Самара", "Ростов-на-Дону", "Пермь", "Воронеж", "Томск", "Иннополис"].map((c) => ({
  value: c,
  label: c,
}));

/** Блок фильтров: по умолчанию свёрнут; содержимое монтируется при раскрытии. */
function Group({ title, tip, count, children }: { title: string; tip?: ReactNode; count?: number; children: ReactNode }) {
  // Заполненный блок раскрыт сам: видно, что уже задано.
  const [open, setOpen] = useState(!!count);
  useEffect(() => {
    if (count) setOpen(true);
  }, [count]);
  const id = useId();
  return (
    <section className="border-t border-hairline pt-3 first:border-t-0 first:pt-0" aria-label={title}>
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((v) => !v)}
          className="flex min-h-9 flex-1 items-center justify-between gap-2 rounded-md text-left focus-visible:outline-2 focus-visible:outline-brand"
        >
          <span className="flex items-center gap-2 font-mono text-12 font-semibold uppercase tracking-wide text-muted">
            {title}
            {count ? <span className="num rounded-full bg-brand px-1.5 text-11 text-on-brand">{count}</span> : null}
          </span>
          <ChevronDown aria-hidden className={cn("size-4 text-muted transition-transform", open && "rotate-180")} />
        </button>
        {tip}
      </div>
      {open && (
        <div id={id} className="mt-2.5 grid gap-2.5">
          {children}
        </div>
      )}
    </section>
  );
}

function Check({ checked, onChange, children, testId }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; testId?: string }) {
  const id = useId();
  return (
    <div className="flex min-h-8 items-center gap-3">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} data-testid={testId} />
      <label htmlFor={id} className="cursor-pointer text-14 leading-snug">
        {children}
      </label>
    </div>
  );
}

const toggle = (xs: string[], x: string, on: boolean) => (on ? (xs.includes(x) ? xs : [...xs, x]) : xs.filter((y) => y !== x));

/**
 * Панель фильтров поиска сотрудников: профессия (все профессии системы), грейд, доверие, «только
 * подтверждённые», ФСП, регион и переезд, ожидания, формат. На < 1024 px тот же блок — в Sheet.
 */
export function MatchFilters({
  c,
  onChange,
  onReset,
  professions,
  skillSuggest,
  skillName,
  className,
}: {
  c: Criteria;
  onChange: (next: Criteria) => void;
  onReset: () => void;
  professions: ProfessionOption[];
  /** Подсказки навыков и подписи выбранных (фильтр «Навыки»). */
  skillSuggest?: SkillSource;
  skillName?: (slug: string) => string;
  className?: string;
}) {
  const set = <K extends keyof Criteria>(k: K, v: Criteria[K]) => onChange({ ...c, [k]: v });
  return (
    <section aria-label={T.filters} className={cn("grid gap-5", className)} data-testid="match-filters">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-16 font-semibold">
          {T.filters}
          {filterCount(c) > 0 && <span className="num ml-2 font-mono text-14 text-brand-fg">· {filterCount(c)}</span>}
        </h2>
        <button type="button" onClick={onReset} className="min-h-8 rounded-md px-1 text-14 font-medium text-brand-fg hover:underline focus-visible:outline-2 focus-visible:outline-brand">
          {T.reset}
        </button>
      </div>

      {skillSuggest && (
        <Group title={T.skills} count={c.skills.length}>
          <SkillInput
            aria-label={T.skillsAdd}
            placeholder={T.skillsPlaceholder}
            allowNew={false}
            suggest={skillSuggest}
            value={c.skills.map((x) => ({ value: x, label: skillName?.(x) ?? x }))}
            onChange={(v) => set("skills", v.map((x) => x.value))}
            data-testid="filter-skills"
          />
        </Group>
      )}

      <Group title={T.profession} count={c.profession ? 1 : 0}>
        <ProfessionInput
          value={c.profession}
          onChange={(v) => set("profession", v)}
          professions={professions}
          suggest={suggestProfessions}
          placeholder={T.professionAny}
          clearable
          aria-label={T.profession}
          data-testid="filter-profession"
        />
      </Group>

      <Group title={T.grade} tip={<Gi k="grade" />} count={c.grades.length + (c.confirmed ? 1 : 0)}>
        <div className="flex flex-wrap gap-2" role="group" aria-label={T.grade}>
          {TEST_GRADES.map((g) => {
            const on = c.grades.includes(g);
            return (
              <button
                key={g}
                type="button"
                aria-pressed={on}
                data-testid={`filter-grade-${g}`}
                onClick={() => set("grades", on ? c.grades.filter((x) => x !== g) : gradeSpan([...c.grades, g]))}
                className={cn(
                  "min-h-9 rounded-md border px-3 font-mono text-13 font-semibold focus-visible:outline-2 focus-visible:outline-brand",
                  on ? "border-brand bg-brand text-on-brand" : "border-hairline bg-card text-ink hover:border-brand-mid",
                )}
              >
                {GRADE_LABEL[g] ?? g}
              </button>
            );
          })}
        </div>
        <p className="text-12 text-muted">{T.gradeHint}</p>
        <Check checked={c.confirmed} onChange={(v) => set("confirmed", v)} testId="filter-confirmed">
          {T.confirmed}
        </Check>
        <p className="-mt-1 pl-8 text-12 text-muted">{T.confirmedHint}</p>
      </Group>

      <Group title={T.trust} tip={<Gi k="trust" />} count={c.trust !== null ? 1 : 0}>
        <SegmentedControl
          label={T.trust}
          value={c.trust === null ? "any" : String(c.trust)}
          onValueChange={(v) => set("trust", v === "any" ? null : Number(v))}
          options={TRUST_OPTIONS}
          className="flex-wrap"
        />
        <p className="text-12 text-muted">{T.trustHint}</p>
      </Group>

      <Group title={T.fsp} count={c.fsp ? 1 : 0}>
        <Check checked={c.fsp} onChange={(v) => set("fsp", v)} testId="filter-fsp">
          {T.fspOnly}
        </Check>
      </Group>

      <Group title={T.region} count={c.cities.length + (c.relocation ? 1 : 0)}>
        <Combobox
          multiple
          creatable
          createLabel={(q) => `Добавить «${q}»`}
          value={c.cities}
          options={CITIES}
          selectedOptions={c.cities.map((x) => ({ value: x, label: x }))}
          onChange={(v) => set("cities", v)}
          placeholder={T.regionPlaceholder}
          aria-label={T.region}
          data-testid="filter-region"
        />
        <Check checked={c.relocation} onChange={(v) => set("relocation", v)} testId="filter-relocation">
          {T.relocation}
        </Check>
      </Group>

      <Group title={T.salary} count={c.salaryFrom !== null || c.salaryTo !== null ? 1 : 0}>
        <SalaryRangeInput
          value={{ from: c.salaryFrom, to: c.salaryTo }}
          onChange={(v) => onChange({ ...c, salaryFrom: v.from || null, salaryTo: v.to })}
          fromLabel={T.salaryFrom}
          toLabel={T.salaryTo}
          fromTestId="filter-salary-from"
          toTestId="filter-salary-to"
        />
      </Group>

      <Group title={T.format} count={c.formats.length}>
        {FORMATS.map((k) => (
          <Check key={k} checked={c.formats.includes(k)} onChange={(on) => set("formats", toggle(c.formats, k, on))}>
            {FORMAT_LABEL[k]}
          </Check>
        ))}
      </Group>
    </section>
  );
}
