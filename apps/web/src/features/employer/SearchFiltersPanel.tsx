import { useId, useMemo, type ReactNode } from "react";

import { Checkbox, SectionLabel, SegmentedControl, Select, Separator, SkillInput, Slider, cn, formatRub, localSkillSource } from "@fsp/ui";

import { GRADE_LABEL, ROLE_LABEL } from "@/features/profile/text";
import { GRADES, type SearchForm } from "./search-model";
import { BUDGET_MAX, BUDGET_MIN, BUDGET_STEP, FORMAT_LABEL, SEARCH_TEXT as T } from "./text";

const TRUST_OPTIONS = [
  { value: "any", label: T.trustAny },
  ...[1, 2, 3].map((n) => ({
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

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="grid gap-3">
      <legend className="mb-3">
        <SectionLabel>{title}</SectionLabel>
      </legend>
      {children}
    </fieldset>
  );
}

function Check({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  const id = useId();
  return (
    <div className="flex min-h-8 items-center gap-3">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      <label htmlFor={id} className="cursor-pointer text-14 leading-snug">
        {children}
      </label>
    </div>
  );
}

const toggle = (xs: string[], x: string, on: boolean) => (on ? (xs.includes(x) ? xs : [...xs, x]) : xs.filter((y) => y !== x));

/**
 * Фильтры слева на экране A: вакансия, роль, минимальное доверие, ФСП, формат, грейд, бюджет, навыки.
 * На ≤1024 px тот же блок открывается в Sheet.
 */
export function SearchFiltersPanel({
  form,
  set,
  onReset,
  vacancies,
  vacancyId,
  onPickVacancy,
  skills,
  skillName,
  className,
}: {
  form: SearchForm;
  set: <K extends keyof SearchForm>(k: K, v: SearchForm[K]) => void;
  onReset: () => void;
  vacancies: { id: string; title: string }[];
  vacancyId: string | null;
  onPickVacancy: (id: string) => void;
  skills: { slug: string; name: string }[];
  skillName: (slug: string) => string;
  className?: string;
}) {
  const budget = form.salaryMax ?? BUDGET_MAX;
  const suggest = useMemo(() => localSkillSource(skills), [skills]);
  return (
    <section aria-label={T.filters} className={cn("grid gap-5", className)}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-16 font-semibold">{T.filters}</h2>
        <button type="button" onClick={onReset} className="min-h-8 rounded-md px-1 text-14 font-medium text-brand-fg hover:underline focus-visible:outline-2 focus-visible:outline-brand">
          {T.reset}
        </button>
      </div>

      {vacancies.length > 0 && (
        <div className="grid gap-1.5 text-13 font-medium text-muted">
          <span>{T.vacancy}</span>
          <Select
            aria-label="Вакансия"
            value={vacancyId ?? ""}
            onChange={(v) => onPickVacancy(v ?? "")}
            options={[{ value: "", label: T.vacancyNone }, ...vacancies.map((v) => ({ value: v.id, label: v.title }))]}
            className="font-normal"
          />
        </div>
      )}

      <div className="grid gap-1.5 text-13 font-medium text-muted">
        <span>{T.role}</span>
        <Select
          aria-label="Роль"
          value={form.roles[0] ?? ""}
          onChange={(v) => set("roles", v ? [v] : [])}
          options={[{ value: "", label: T.any }, ...Object.entries(ROLE_LABEL).map(([k, v]) => ({ value: k, label: v }))]}
          className="font-normal"
        />
      </div>

      <Separator />
      <Group title={T.trust}>
        <SegmentedControl
          label={T.trust}
          value={form.minTrust === null ? "any" : String(form.minTrust)}
          onValueChange={(v) => set("minTrust", v === "any" ? null : Number(v))}
          options={TRUST_OPTIONS}
          className="flex-wrap"
        />
        <p className="text-12 text-muted">{T.trustHint}</p>
      </Group>

      <Separator />
      <Group title={T.fsp}>
        <Check checked={form.fspOnly} onChange={(v) => set("fspOnly", v)}>
          {T.fspOnly}
        </Check>
        <Check checked={form.activeOnly} onChange={(v) => set("activeOnly", v)}>
          {T.activeOnly}
        </Check>
      </Group>

      <Separator />
      <Group title={T.format}>
        {Object.entries(FORMAT_LABEL).map(([k, v]) => (
          <Check key={k} checked={form.formats.includes(k)} onChange={(on) => set("formats", toggle(form.formats, k, on))}>
            {v}
          </Check>
        ))}
      </Group>

      <Separator />
      <Group title={T.grade}>
        {GRADES.map((g) => (
          <Check key={g} checked={form.grades.includes(g)} onChange={(on) => set("grades", toggle(form.grades, g, on))}>
            {GRADE_LABEL[g]}
          </Check>
        ))}
      </Group>

      <Separator />
      <Group title={T.budget}>
        <p className="font-mono text-16 font-semibold" aria-live="polite">
          {form.salaryMax === null ? T.budgetAny : `до ${formatRub(form.salaryMax)}`}
        </p>
        <Slider
          aria-label={T.budget}
          min={BUDGET_MIN}
          max={BUDGET_MAX}
          step={BUDGET_STEP}
          value={[Math.min(Math.max(budget, BUDGET_MIN), BUDGET_MAX)]}
          onValueChange={([v]) => set("salaryMax", v === undefined || v >= BUDGET_MAX ? null : v)}
        />
        <div className="flex justify-between font-mono text-11 text-muted">
          <span>{formatRub(BUDGET_MIN)}</span>
          <span>{formatRub(BUDGET_MAX)}+</span>
        </div>
      </Group>

      <Separator />
      <Group title={T.skills}>
        <SkillInput
          aria-label="Добавить навык"
          placeholder={T.addSkill}
          allowNew={false}
          suggest={suggest}
          value={form.skills.map((s) => ({ value: s, label: skillName(s) }))}
          onChange={(v) => set("skills", v.map((x) => x.value))}
        />
      </Group>
    </section>
  );
}
