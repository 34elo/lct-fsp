import { useId, type ReactNode } from "react";

import { Checkbox, Combobox, ProfessionInput, SalaryRangeInput, SectionLabel, SegmentedControl, Separator, cn, type ProfessionOption } from "@fsp/ui";

import { GRADE_LABEL } from "@/features/profile/text";
import { Gi } from "@/shared/Gloss";
import { suggestProfessions } from "@/shared/lib/skills";
import { FORMATS, TEST_GRADES, gradeSpan, type Criteria } from "./query-model";
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

function Group({ title, tip, children }: { title: string; tip?: ReactNode; children: ReactNode }) {
  return (
    <fieldset className="grid gap-2.5">
      <legend className="mb-2.5 flex items-center gap-1">
        <SectionLabel>{title}</SectionLabel>
        {tip}
      </legend>
      {children}
    </fieldset>
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
 * Панель фильтров поиска сотрудников (E39-21): профессия (все профессии системы), грейд, доверие, «только
 * подтверждённые», ФСП, регион и переезд, ожидания, формат. На < 1024 px тот же блок — в Sheet.
 */
export function MatchFilters({
  c,
  onChange,
  onReset,
  professions,
  className,
}: {
  c: Criteria;
  onChange: (next: Criteria) => void;
  onReset: () => void;
  professions: ProfessionOption[];
  className?: string;
}) {
  const set = <K extends keyof Criteria>(k: K, v: Criteria[K]) => onChange({ ...c, [k]: v });
  return (
    <section aria-label={T.filters} className={cn("grid gap-5", className)} data-testid="match-filters">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-16 font-semibold">{T.filters}</h2>
        <button type="button" onClick={onReset} className="min-h-8 rounded-md px-1 text-14 font-medium text-brand-fg hover:underline focus-visible:outline-2 focus-visible:outline-brand">
          {T.reset}
        </button>
      </div>

      <Group title={T.profession}>
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

      <Separator />
      <Group title={T.grade} tip={<Gi k="grade" />}>
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

      <Separator />
      <Group title={T.trust} tip={<Gi k="trust" />}>
        <SegmentedControl
          label={T.trust}
          value={c.trust === null ? "any" : String(c.trust)}
          onValueChange={(v) => set("trust", v === "any" ? null : Number(v))}
          options={TRUST_OPTIONS}
          className="flex-wrap"
        />
        <p className="text-12 text-muted">{T.trustHint}</p>
      </Group>

      <Separator />
      <Group title={T.fsp}>
        <Check checked={c.fsp} onChange={(v) => set("fsp", v)} testId="filter-fsp">
          {T.fspOnly}
        </Check>
      </Group>

      <Separator />
      <Group title={T.region}>
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

      <Separator />
      <Group title={T.salary}>
        <SalaryRangeInput
          value={{ from: c.salaryFrom, to: c.salaryTo }}
          onChange={(v) => onChange({ ...c, salaryFrom: v.from || null, salaryTo: v.to })}
          fromLabel={T.salaryFrom}
          toLabel={T.salaryTo}
          fromTestId="filter-salary-from"
          toTestId="filter-salary-to"
        />
      </Group>

      <Separator />
      <Group title={T.format}>
        {FORMATS.map((k) => (
          <Check key={k} checked={c.formats.includes(k)} onChange={(on) => set("formats", toggle(c.formats, k, on))}>
            {FORMAT_LABEL[k]}
          </Check>
        ))}
      </Group>
    </section>
  );
}
