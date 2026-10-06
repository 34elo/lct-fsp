import { Badge, Button, Card, Field, FieldInput, Input, SectionLabel, Skeleton } from "@fsp/ui";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  getHistoryAssessmentHistoryGetQueryKey,
  useCreateAttemptAssessmentAttemptsPost,
  useGetSurveyAssessmentSurveyGet,
  usePutSurveyAssessmentSurveyPut,
} from "@/api/endpoints/assessment/assessment";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { SurveyIn, TestGrade, WorkFormat } from "@/api/model";
import { cn } from "@/shared/lib/cn";
import { addStack, salaryError } from "./model";
import { FORMAT_OPTIONS, GRADE_CARDS, STEPS, T } from "./text";
import { ErrorLine, LoadError, Page } from "./ui";

const isGrade = (g: string | null | undefined): g is TestGrade => GRADE_CARDS.some((c) => c.grade === g);

function Choice({ checked, onSelect, title, text, testid, children }: { checked: boolean; onSelect: () => void; title: string; text?: string; testid: string; children?: React.ReactNode }) {
  return (
    <label
      className={cn(
        "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border bg-card p-3 text-left",
        checked ? "border-brand bg-tint-50" : "border-hairline hover:border-brand-mid",
      )}
    >
      <input type="radio" className="mt-1 size-4 accent-[var(--brand)]" checked={checked} onChange={onSelect} data-testid={testid} />
      <span className="flex flex-col gap-0.5">
        <span className="text-14 font-semibold">{title}</span>
        {text && <span className="text-13 text-muted">{text}</span>}
        {children}
      </span>
    </label>
  );
}

/** S1: опрос и выбор грейда. На 1440 — все шаги на одном экране, на 375 — по одному. */
export default function Survey() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const sq = useGetSurveyAssessmentSurveyGet();
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const survey = sq.data?.status === 200 ? sq.data.data : undefined;
  const professions = useMemo(() => (pq.data?.status === 200 ? pq.data.data.professions : []), [pq.data]);

  const [step, setStep] = useState(0);
  const [industry, setIndustry] = useState("");
  const [profession, setProfession] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [stackDraft, setStackDraft] = useState("");
  const [formats, setFormats] = useState<WorkFormat[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [grade, setGrade] = useState<TestGrade | "">("");
  const [touched, setTouched] = useState(false);
  const [done, setDone] = useState(false);

  // Предзаполнение один раз: опрос или черновик из анкеты, затем параметры ссылки из навигатора.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    if (filled || !survey) return;
    setIndustry(survey.industry ?? "");
    setProfession(params.get("profession") ?? survey.profession ?? "");
    setStack(survey.stack ?? []);
    setFormats((survey.formats ?? []) as WorkFormat[]);
    setFrom(survey.salary_from != null ? String(survey.salary_from) : "");
    setTo(survey.salary_to != null ? String(survey.salary_to) : "");
    const g = params.get("grade") ?? survey.declared_grade;
    setGrade(isGrade(g) ? g : "");
    setFilled(true);
  }, [survey, filled, params]);

  const put = usePutSurveyAssessmentSurveyPut();
  const create = useCreateAttemptAssessmentAttemptsPost();
  const busy = put.isPending || create.isPending;
  const rangeBad = salaryError(from, to);

  const body = (): SurveyIn => ({
    industry: industry.trim() || null,
    profession,
    stack,
    formats,
    salary_from: from ? Number(from) : null,
    salary_to: to ? Number(to) : null,
    declared_grade: grade || null,
  });

  const valid = !!profession && !rangeBad;

  async function submit(start: boolean) {
    setTouched(true);
    setDone(false);
    create.reset();
    if (!valid || (start && !grade)) return;
    try {
      await put.mutateAsync({ data: body() });
      await qc.invalidateQueries({ queryKey: getHistoryAssessmentHistoryGetQueryKey() });
      if (!start) {
        setDone(true);
        return;
      }
      const r = await create.mutateAsync({ data: { profession, declared_grade: grade as TestGrade } });
      if (r.status === 201) nav(`/me/assessment/attempts/${r.data.id}`);
    } catch {
      // Ошибки показаны через put.error / create.error.
    }
  }

  const section = (i: number) => cn(i === step ? "flex" : "hidden", "flex-col gap-3 md:flex");
  const mobileNav = (i: number) => (
    <div className="flex gap-2 md:hidden">
      {i > 0 && (
        <Button variant="outline" onClick={() => setStep(i - 1)} data-testid="assessment-step-back">
          {T.back}
        </Button>
      )}
      {i < STEPS.length - 1 && (
        <Button onClick={() => setStep(i + 1)} data-testid="assessment-step-next">
          {T.next}
        </Button>
      )}
    </div>
  );

  return (
    <Page>
      <header className="flex flex-col gap-1">
        <h1 className="font-mono text-2xl font-semibold">{T.surveyTitle}</h1>
        <p className="text-14 text-muted">{T.surveyLead}</p>
        <p className="text-13 text-muted md:hidden" data-testid="assessment-step-counter">
          {T.stepOf(step + 1, STEPS.length)}
        </p>
      </header>

      {sq.isPending || pq.isPending ? (
        <div role="status" aria-label={T.loading} className="flex flex-col gap-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-40" />
        </div>
      ) : sq.isError || pq.isError ? (
        <LoadError error={sq.error ?? pq.error} onRetry={() => (sq.isError ? sq.refetch() : pq.refetch())} />
      ) : (
        <Card className="flex flex-col gap-5 p-5" data-testid="assessment-survey">
          {survey?.prefilled && (
            <Badge variant="dashed" data-testid="assessment-prefilled" className="self-start">
              {T.prefilled}
            </Badge>
          )}

          <div className={section(0)}>
            <SectionLabel>1. {T.industry}</SectionLabel>
            <Field label={T.industry} hint={T.industryHint}>
              <FieldInput value={industry} onChange={(e) => setIndustry(e.target.value)} data-testid="assessment-industry" />
            </Field>
            {mobileNav(0)}
          </div>

          <div className={section(1)}>
            <SectionLabel>2. {T.profession}</SectionLabel>
            <p className="text-16 font-semibold md:hidden">{T.professionQ}</p>
            <div role="radiogroup" aria-label={T.profession} className="grid gap-2 sm:grid-cols-2">
              {professions.map((p) => (
                <Choice key={p.slug} checked={profession === p.slug} onSelect={() => setProfession(p.slug)} title={p.title} testid={`assessment-profession-${p.slug}`} />
              ))}
            </div>
            {touched && !profession && (
              <p role="alert" className="text-13 text-error">
                {T.needProfession}
              </p>
            )}
            {mobileNav(1)}
          </div>

          <div className={section(2)}>
            <SectionLabel>3. {T.stack}</SectionLabel>
            <p className="text-16 font-semibold md:hidden">{T.stackQ}</p>
            <p className="text-13 text-muted">{T.stackHint}</p>
            <ul className="flex flex-wrap gap-2" data-testid="assessment-stack">
              {stack.map((s) => (
                <li key={s}>
                  <button
                    type="button"
                    aria-label={T.stackRemove(s)}
                    onClick={() => setStack(stack.filter((x) => x !== s))}
                    className="inline-flex min-h-11 items-center gap-1 rounded-md border border-tint-200 bg-tint-50 px-2.5 font-mono text-13 text-brand-fg sm:min-h-8"
                  >
                    {s} <span aria-hidden>×</span>
                  </button>
                </li>
              ))}
            </ul>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                setStack(addStack(stack, stackDraft));
                setStackDraft("");
              }}
            >
              <Input
                aria-label={T.stackAdd}
                placeholder={T.stackAdd}
                value={stackDraft}
                onChange={(e) => setStackDraft(e.target.value)}
                data-testid="assessment-stack-input"
              />
              <Button type="submit" variant="outline" data-testid="assessment-stack-add">
                {T.stackAddBtn}
              </Button>
            </form>
            {mobileNav(2)}
          </div>

          <div className={section(3)}>
            <SectionLabel>4. {T.formats} · {T.salary}</SectionLabel>
            <div className="flex flex-wrap gap-2" role="group" aria-label={T.formats}>
              {FORMAT_OPTIONS.map((f) => {
                const on = formats.includes(f.value);
                return (
                  <button
                    key={f.value}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setFormats(on ? formats.filter((x) => x !== f.value) : [...formats, f.value])}
                    data-testid={`assessment-format-${f.value}`}
                    className={cn(
                      "min-h-11 rounded-lg border px-4 text-14 font-medium",
                      on ? "border-brand bg-brand text-on-brand" : "border-hairline bg-card hover:border-brand-mid",
                    )}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label={T.salaryFrom} error={rangeBad ? T.invalidRange : undefined}>
                <FieldInput type="number" inputMode="numeric" min={0} value={from} onChange={(e) => setFrom(e.target.value)} data-testid="assessment-salary-from" />
              </Field>
              <Field label={T.salaryTo}>
                <FieldInput type="number" inputMode="numeric" min={0} value={to} onChange={(e) => setTo(e.target.value)} data-testid="assessment-salary-to" />
              </Field>
            </div>
            {mobileNav(3)}
          </div>

          <div className={section(4)}>
            <SectionLabel>5. {T.gradeQ}</SectionLabel>
            <div role="radiogroup" aria-label={T.gradeQ} className="grid gap-2 md:grid-cols-3">
              {GRADE_CARDS.map((c) => (
                <Choice
                  key={c.grade}
                  checked={grade === c.grade}
                  onSelect={() => setGrade(c.grade)}
                  title={c.grade === "junior" ? "Junior" : c.grade === "middle" ? "Middle" : "Senior"}
                  text={c.lead}
                  testid={`assessment-grade-${c.grade}`}
                >
                  <span className="font-mono text-12 text-muted">{T.gradeMinutes(c.minutes)}</span>
                </Choice>
              ))}
            </div>
            <p className="text-13 text-muted">{T.gradeHint}</p>
            {touched && !grade && (
              <p role="alert" className="text-13 text-error" data-testid="assessment-need-grade">
                {T.needGrade}
              </p>
            )}
            {mobileNav(4)}
          </div>

          {put.isError && <ErrorLine error={put.error} data-testid="assessment-survey-error" />}
          {create.isError && <ErrorLine error={create.error} data-testid="assessment-start-error" />}
          {done && (
            <p role="status" className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success" data-testid="assessment-saved">
              {T.saved}
            </p>
          )}

          <div className={cn("flex-wrap items-center gap-2", step === STEPS.length - 1 ? "flex" : "hidden md:flex")}>
            <Button variant="outline" loading={put.isPending && !create.isPending} disabled={busy} onClick={() => submit(false)} data-testid="assessment-save">
              {T.save}
            </Button>
            <Button loading={create.isPending} disabled={busy} onClick={() => submit(true)} data-testid="assessment-start">
              {T.saveAndStart}
            </Button>
            <Link to="/me/assessment/history" className="text-14 font-semibold text-brand-fg underline" data-testid="assessment-history-link">
              {T.historyLink}
            </Link>
          </div>
          <p className="text-12 text-muted">{T.historyHint}</p>
        </Card>
      )}
    </Page>
  );
}
