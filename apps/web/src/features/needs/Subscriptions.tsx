import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, Combobox, EmptyState, ErrorState, NumberInput, SectionLabel, Select, Skeleton, formatRub } from "@fsp/ui";

import {
  getListSubscriptionsSubscriptionsGetQueryKey,
  useCreateSubscriptionSubscriptionsPost,
  useDeleteSubscriptionSubscriptionsSubscriptionIdDelete,
  useListSubscriptionsSubscriptionsGet,
} from "@/api/endpoints/subscriptions/subscriptions";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import { TestGrade, type SkillMin, type SubscriptionOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { GRADE_LABEL, ROLE_LABEL, roleLabel } from "@/features/profile/text";
import { parseRub } from "@/features/offers/offer-model";
import { SUB_TEXT as T } from "./text";

const LEVELS = [1, 2, 3, 4];

function describe(s: SubscriptionOut, skillName: (slug: string) => string): string {
  return [
    s.grades.length ? s.grades.map((g) => GRADE_LABEL[g] ?? g).join(", ") : T.anyGrade,
    s.formats.length ? s.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ") : null,
    s.salary_max ? T.budget(formatRub(s.salary_max)) : null,
    s.only_confirmed ? T.confirmedOnly : null,
    ...s.skills.map((k) => `${skillName(k.slug)} · ${T.level(k.min_level ?? 1)}`),
  ]
    .filter(Boolean)
    .join(" · ");
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? (T.errors[e.code ?? ""] ?? T.fallbackError) : T.fallbackError;
}

/** Подписки работодателя на категорию (E33-4): форма фильтра и список подписок. */
export default function Subscriptions() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const list = useListSubscriptionsSubscriptionsGet();
  const taxonomy = useGetTaxonomyTaxonomyGet();
  const skills = useMemo(() => (taxonomy.data?.data as { skills?: { slug: string; name: string }[] } | undefined)?.skills ?? [], [taxonomy.data]);
  const skillName = (slug: string) => skills.find((s) => s.slug === slug)?.name ?? slug;

  const initialGrade = params.get("grade");
  const [profession, setProfession] = useState(params.get("profession") ?? "backend");
  const [grades, setGrades] = useState<string[]>(initialGrade && initialGrade in TestGrade ? [initialGrade] : []);
  const [formats, setFormats] = useState<string[]>([]);
  const [salary, setSalary] = useState("");
  const [onlyConfirmed, setOnlyConfirmed] = useState(false);
  const [picked, setPicked] = useState<SkillMin[]>([]);
  const [skillSlug, setSkillSlug] = useState("");
  const [skillLevel, setSkillLevel] = useState(2);

  const refresh = () => void qc.invalidateQueries({ queryKey: getListSubscriptionsSubscriptionsGetQueryKey() });
  const create = useCreateSubscriptionSubscriptionsPost({
    mutation: {
      onSuccess: () => {
        refresh();
        setPicked([]);
        setSalary("");
      },
    },
  });
  const remove = useDeleteSubscriptionSubscriptionsSubscriptionIdDelete({ mutation: { onSuccess: refresh } });

  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const addSkill = () => {
    if (!skillSlug || picked.some((s) => s.slug === skillSlug) || picked.length >= 10) return;
    setPicked([...picked, { slug: skillSlug, min_level: skillLevel }]);
    setSkillSlug("");
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (create.isPending) return;
    create.mutate({
      data: {
        profession,
        grades: grades as (typeof TestGrade)[keyof typeof TestGrade][],
        skills: picked,
        salary_max: parseRub(salary),
        formats,
        only_confirmed: onlyConfirmed,
      },
    });
  };
  const subs = list.data?.status === 200 ? list.data.data : [];
  const chip = "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-hairline bg-card px-3 text-14 has-[:checked]:border-brand has-[:checked]:bg-tint-50";

  return (
    <main className="mx-auto grid w-full max-w-5xl gap-6 p-4 md:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <header className="grid gap-1 lg:col-span-2">
        <h1 className="font-mono text-24 font-semibold">{T.title}</h1>
        <p className="text-14 text-muted">{T.lead}</p>
      </header>

      <form onSubmit={submit} aria-label={T.new} className="grid content-start gap-4 rounded-xl border border-hairline bg-card p-4 md:p-5">
        <h2 className="font-mono text-17 font-semibold">{T.new}</h2>
        <div className="grid gap-1 text-sm font-semibold">
          <span>{T.profession}</span>
          <Select
            aria-label={T.profession}
            value={profession}
            onChange={(v) => v && setProfession(v)}
            options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ value: k, label: v }))}
            className="font-normal"
          />
        </div>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-semibold">{T.grades}</legend>
          <div className="flex flex-wrap gap-2">
            {Object.values(TestGrade).map((g) => (
              <label key={g} className={chip}>
                <input type="checkbox" checked={grades.includes(g)} onChange={() => setGrades(toggle(grades, g))} className="size-4 accent-brand" />
                {GRADE_LABEL[g]}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-semibold">{T.formats}</legend>
          <div className="flex flex-wrap gap-2">
            {Object.entries(FORMAT_LABEL).map(([k, v]) => (
              <label key={k} className={chip}>
                <input type="checkbox" checked={formats.includes(k)} onChange={() => setFormats(toggle(formats, k))} className="size-4 accent-brand" />
                {v}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="grid gap-1 text-sm font-semibold">
          <span>{T.salaryMax}</span>
          <NumberInput
            aria-label={T.salaryMax}
            value={salary ? Number(salary) : null}
            onChange={(v) => setSalary(v == null ? "" : String(v))}
            min={0}
            grouped
            stepper={false}
            suffix="₽"
          />
          <span className="text-xs font-normal text-muted">{T.salaryHint}</span>
        </div>
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-sm font-semibold">{T.skills}</legend>
          <div className="flex flex-wrap items-end gap-2">
            <div className="grid min-w-0 flex-1 basis-48 gap-1 text-xs text-muted">
              <span>{T.skillPick}</span>
              <Combobox
                aria-label={T.skillPick}
                placeholder="—"
                value={skillSlug || null}
                onChange={(v) => setSkillSlug(v ?? "")}
                options={skills.map((s) => ({ value: s.slug, label: s.name }))}
                className="text-ink"
              />
            </div>
            <div className="grid gap-1 text-xs text-muted">
              <span>{T.skillLevel}</span>
              <Select
                aria-label={T.skillLevel}
                value={String(skillLevel)}
                onChange={(v) => v && setSkillLevel(Number(v))}
                options={LEVELS.map((l) => ({ value: String(l), label: `≥ ${l}` }))}
                className="w-24 text-ink"
              />
            </div>
            <Button type="button" variant="outline" onClick={addSkill} disabled={!skillSlug}>{T.skillAdd}</Button>
          </div>
          {picked.length > 0 && (
            <ul className="flex flex-wrap gap-1.5">
              {picked.map((s) => (
                <li key={s.slug}>
                  <button
                    type="button"
                    aria-label={`Убрать навык ${skillName(s.slug)}`}
                    onClick={() => setPicked(picked.filter((x) => x.slug !== s.slug))}
                    className="rounded-md border border-tint-200 bg-tint-50 px-2.5 py-1 font-mono text-12 text-brand-deep dark:text-brand-mid"
                  >
                    {skillName(s.slug)} · ≥ {s.min_level} ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </fieldset>
        <label className="flex items-start gap-2 text-14">
          <input type="checkbox" checked={onlyConfirmed} onChange={(e) => setOnlyConfirmed(e.target.checked)} className="mt-1 size-4 accent-brand" />
          {T.onlyConfirmed}
        </label>
        {create.isError && <ErrorNote>{errorText(create.error)}</ErrorNote>}
        <Button type="submit" size="lg" loading={create.isPending}>{create.isPending ? T.saving : T.submit}</Button>
      </form>

      <section aria-label={T.mine} className="grid content-start gap-3">
        <SectionLabel>{T.mine}</SectionLabel>
        {list.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-24" />}
        {list.isError && <ErrorState title={T.loadError} onRetry={() => void list.refetch()} />}
        {list.isSuccess && subs.length === 0 && <EmptyState title={T.empty} description={T.emptyHint} />}
        {remove.isError && <ErrorNote>{errorText(remove.error)}</ErrorNote>}
        <ul className="grid gap-3">
          {subs.map((s) => (
            <li key={s.id} className="flex items-start justify-between gap-3 rounded-xl border border-hairline bg-card p-4">
              <div className="grid min-w-0 gap-1">
                <h3 className="font-mono text-16 font-semibold">{roleLabel(s.profession)}</h3>
                <p className="break-words text-13 text-muted">{describe(s, skillName)}</p>
              </div>
              <Button variant="outline" size="sm" aria-label={T.removeLabel(roleLabel(s.profession))} loading={remove.isPending && remove.variables?.subscriptionId === s.id} onClick={() => remove.mutate({ subscriptionId: s.id })}>
                {T.remove}
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
