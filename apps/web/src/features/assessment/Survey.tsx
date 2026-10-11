import { Button, Chips, cn, H1, Lbl, Num, Panel, SalaryRangeInput, Skeleton, SkillInput, StatusTag, Tag } from "@fsp/ui";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import {
  getHistoryAssessmentHistoryGetQueryKey,
  useCreateAttemptAssessmentAttemptsPost,
  useGetSurveyAssessmentSurveyGet,
  useHistoryAssessmentHistoryGet,
  usePutSurveyAssessmentSurveyPut,
} from "@/api/endpoints/assessment/assessment";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { SurveyIn, TestGrade, WorkFormat } from "@/api/model";
import { Gi, Gloss } from "@/shared/Gloss";
import { useSkillSource } from "@/shared/lib/skills";
import { addStack, isFuture, salaryError } from "./model";
import { FORMAT_OPTIONS, GRADE, GRADE_CARDS, T, dateShort } from "./text";
import { ChoiceCards, ErrorLine, FlowSteps, LoadError, Page } from "./ui";

const isGrade = (g: string | null | undefined): g is TestGrade => GRADE_CARDS.some((c) => c.grade === g);
const GRADE_ORDER: TestGrade[] = ["junior", "middle", "senior"];

function Fld({ label, resume, tid, children }: { label: React.ReactNode; resume?: boolean; tid?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Lbl>{label}</Lbl>
        {resume && (
          <StatusTag state="claimed" data-testid={tid}>
            {T.fromResume}
          </StatusTag>
        )}
      </div>
      {children}
    </div>
  );
}

type Step = 1 | 2;

/**
 * S1: поток «Шаг 1. Направление и навыки → Шаг 2. Грейд и ожидания → Шаг 3. Тест».
 * Новый кандидат попадает сюда сразу после регистрации; «Начать тест» сохраняет ответы и открывает
 * первое задание. Шаг 2 открывается сразу, если направление уже сохранено или пришло в ссылке
 * (навигатор, результат теста); `?step=1` — правка направления и навыков из профиля.
 */
export default function Survey() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const sq = useGetSurveyAssessmentSurveyGet();
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const hq = useHistoryAssessmentHistoryGet();
  const survey = sq.data?.status === 200 ? sq.data.data : undefined;
  const history = hq.data?.status === 200 ? hq.data.data : undefined;
  const professions = useMemo(() => (pq.data?.status === 200 ? pq.data.data.professions : []), [pq.data]);

  const [step, setStep] = useState<Step>(1);
  const [profession, setProfession] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [formats, setFormats] = useState<WorkFormat[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [grade, setGrade] = useState<TestGrade | "">("");
  const [express, setExpress] = useState(params.get("mode") === "express"); // вход жюри
  const [touched, setTouched] = useState(false);
  const [done, setDone] = useState(false);
  const { suggest } = useSkillSource(profession || undefined);
  const editStep1 = params.get("step") === "1";

  // Предзаполнение один раз: сохранённые ответы или черновик из анкеты, затем параметры ссылки.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    if (filled || !survey) return;
    const p = params.get("profession") ?? survey.profession ?? "";
    setProfession(p);
    setStack(survey.stack ?? []);
    setFormats((survey.formats ?? []) as WorkFormat[]);
    setFrom(survey.salary_from != null ? String(survey.salary_from) : "");
    setTo(survey.salary_to != null ? String(survey.salary_to) : "");
    const g = params.get("grade") ?? survey.declared_grade;
    setGrade(isGrade(g) ? g : "");
    const known = !!p && (!!survey.id || params.has("profession") || params.has("grade"));
    setStep(params.get("step") === "1" ? 1 : params.get("step") === "2" || known ? 2 : 1);
    setFilled(true);
  }, [survey, filled, params]);

  const put = usePutSurveyAssessmentSurveyPut();
  const create = useCreateAttemptAssessmentAttemptsPost();
  const busy = put.isPending || create.isPending;
  const rangeBad = salaryError(from, to);

  // Кулдаун выбранной пары «направление × грейд»: смена грейда (90 дней) или пересдача (30 дней).
  const lockUntil = useMemo(() => {
    if (!history || !grade) return null;
    const dates = [
      ...history.cooldowns.filter((c) => c.profession === profession && c.grade === grade).map((c) => c.next_change_at),
      ...(history.retries ?? []).filter((r) => r.profession === profession && r.grade === grade).map((r) => r.next_attempt_at),
    ].filter((d) => isFuture(d));
    return dates.sort().at(-1) ?? null;
  }, [history, profession, grade]);
  const lowerGrade = grade ? GRADE_ORDER[GRADE_ORDER.indexOf(grade) - 1] : undefined;

  const body = (g: TestGrade | ""): SurveyIn => ({
    industry: survey?.industry ?? null, // отрасль не спрашиваем, прежнее значение сохраняем
    profession,
    stack,
    formats,
    salary_from: from ? Number(from) : null,
    salary_to: to ? Number(to) : null,
    declared_grade: g || null,
  });

  function next() {
    setTouched(true);
    if (!profession) return;
    setTouched(false);
    setDone(false);
    setStep(2);
    window.scrollTo?.({ top: 0 });
  }

  async function submit(start: boolean, as?: TestGrade) {
    setTouched(true);
    setDone(false);
    create.reset();
    const g = as ?? grade;
    if (as) setGrade(as);
    if (!profession || rangeBad || (start && !g)) return;
    try {
      await put.mutateAsync({ data: body(g) });
      void qc.invalidateQueries({ queryKey: getHistoryAssessmentHistoryGetQueryKey() });
      if (!start) {
        setDone(true);
        return;
      }
      const r = await create.mutateAsync({
        data: { profession, declared_grade: g as TestGrade, ...(express ? { mode: "express" as const } : {}) },
      });
      void qc.invalidateQueries({ queryKey: getHistoryAssessmentHistoryGetQueryKey() }); // баннер пути: «продолжить тест»
      if (r.status === 201) nav(`/me/assessment/attempts/${r.data.id}`);
    } catch {
      // Ошибки показаны через put.error / create.error.
    }
  }

  const resume = !!survey?.prefilled;
  const startLabel = lockUntil && lowerGrade ? T.startLower(GRADE[lowerGrade] ?? lowerGrade) : T.startTest;
  const startDisabled = busy || (!!lockUntil && !lowerGrade);
  const onStart = () => (lockUntil && lowerGrade ? submit(true, lowerGrade) : submit(true));

  const savedNote = done && (
    <p role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-success-bg px-3 py-2 text-14 text-success" data-testid="assessment-saved">
      <span>
        {T.saved}. {step === 2 && T.savedLater}
      </span>
      <Link to={step === 1 ? "/me/profile" : "/me"} className="font-semibold underline" data-testid="assessment-later">
        {step === 1 ? T.toProfile : T.toHome}
      </Link>
    </p>
  );

  return (
    <Page>
      <div className="flex flex-col gap-4">
        <FlowSteps current={step} steps={T.flow} label={T.flowLabel} />
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
          <H1 className="max-md:text-[22px]">{T.flow[step - 1]}</H1>
          <Link to="/me/assessment/history" className="text-14 font-semibold text-brand-fg underline" data-testid="assessment-history-link">
            {T.historyLink}
          </Link>
        </div>
        <p className="text-14 text-muted">{step === 1 ? T.step1Lead : T.step2Lead}</p>
      </div>

      {sq.isPending || pq.isPending ? (
        <div role="status" aria-label={T.loading} className="grid gap-3 md:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
      ) : sq.isError || pq.isError ? (
        <LoadError error={sq.error ?? pq.error} onRetry={() => (sq.isError ? sq.refetch() : pq.refetch())} />
      ) : step === 1 ? (
        <div className="flex flex-col gap-6" data-testid="assessment-step-1">
          <Panel className="flex flex-col gap-6" data-testid="assessment-survey">
            <Fld label={<Gloss k="category">{T.direction}</Gloss>} resume={resume} tid="assessment-prefilled">
              <ChoiceCards
                label={T.profession}
                name="assessment-profession"
                value={profession}
                options={professions.map((p) => ({
                  value: p.slug,
                  title: p.title,
                  aside: p.beta ? (
                    <span className="inline-flex shrink-0 items-center gap-1" data-testid={`assessment-beta-${p.slug}`}>
                      <Tag>{T.beta}</Tag>
                      <Gi k="beta" />
                    </span>
                  ) : undefined,
                  text: p.beta ? T.betaHint : undefined,
                }))}
                onChange={(v) => {
                  setProfession(v);
                  setTouched(false);
                }}
                testid={(v) => `assessment-profession-${v}`}
                className="grid-cols-1 sm:grid-cols-2 md:grid-cols-3"
              />
              {touched && !profession && (
                <p role="alert" className="text-13 text-error" data-testid="assessment-need-profession">
                  {T.needProfession}
                </p>
              )}
            </Fld>

            <Fld label={T.skills} resume={resume}>
              <div data-testid="assessment-stack">
                <SkillInput
                  aria-label={T.stackAdd}
                  placeholder={T.stackAdd}
                  value={stack.map((s) => ({ value: s, label: s }))}
                  onChange={(v) => setStack(v.reduce<string[]>((acc, x) => addStack(acc, x.label), []))}
                  suggest={suggest}
                  max={30}
                  data-testid="assessment-stack-input"
                />
              </div>
              <p className="text-12 text-muted">{T.skillsHint}</p>
            </Fld>
          </Panel>

          {put.isError && <ErrorLine error={put.error} data-testid="assessment-survey-error" />}
          {savedNote}
          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={next} disabled={busy} data-testid="assessment-next">
              {T.next}
            </Button>
            {editStep1 && (
              <Button variant="outline" size="lg" loading={put.isPending} disabled={busy} onClick={() => submit(false)} data-testid="assessment-save-step">
                {T.saveStep}
              </Button>
            )}
            <span className="text-12 text-muted">{T.step1Later}</span>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-6" data-testid="assessment-step-2">
          {lockUntil && (
            <Panel className="flex items-center gap-3 bg-tint-50" data-testid="assessment-cooldown">
              <Lbl>{T.nextAttempt(GRADE[grade] ?? grade)}</Lbl>
              <Num className="ml-auto text-18" data-testid="assessment-cooldown-date">
                {dateShort(lockUntil)}
              </Num>
            </Panel>
          )}

          <Panel className="flex flex-col gap-6" data-testid="assessment-survey">
            <Fld label={<Gloss k="grade">{T.gradeLabel}</Gloss>} resume={resume && !!grade}>
              <ChoiceCards
                label={T.gradeQ}
                name="assessment-grade"
                value={grade}
                options={GRADE_CARDS.map((c) => ({
                  value: c.grade,
                  title: GRADE[c.grade] ?? c.grade,
                  aside: <Num className="text-12 text-muted">{T.minutesShort(c.minutes)}</Num>,
                  text: c.lead,
                }))}
                onChange={setGrade}
                testid={(v) => `assessment-grade-${v}`}
                lockedValue={lockUntil ? grade : ""}
                className="grid-cols-1 md:grid-cols-3"
              />
              <p className="text-12 text-muted">{T.gradeHint}</p>
              {touched && !grade && (
                <p role="alert" className="text-13 text-error" data-testid="assessment-need-grade">
                  {T.needGrade}
                </p>
              )}
            </Fld>

            <Fld label={T.format} resume={resume}>
              <Chips role="group" aria-label={T.formats}>
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
                        "min-h-9 rounded-sm border px-3 font-mono text-12 font-medium transition-colors",
                        on ? "border-brand bg-tint-50 text-chip-fg" : "border-hairline bg-card text-muted hover:border-brand-mid",
                      )}
                    >
                      {f.label}
                    </button>
                  );
                })}
              </Chips>
            </Fld>

            <Fld label={T.fork} resume={resume}>
              <SalaryRangeInput
                value={{ from: from ? Number(from) : null, to: to ? Number(to) : null }}
                onChange={(v) => {
                  setFrom(v.from == null ? "" : String(v.from));
                  setTo(v.to == null ? "" : String(v.to));
                }}
                fromLabel={T.salaryFrom}
                toLabel={T.salaryTo}
                invalid={rangeBad}
                fromTestId="assessment-salary-from"
                toTestId="assessment-salary-to"
              />
              {rangeBad && (
                <p role="alert" className="text-12 text-error">
                  {T.invalidRange}
                </p>
              )}
            </Fld>

            <label className="flex cursor-pointer items-center gap-3">
              <input type="checkbox" className="peer sr-only" checked={express} onChange={(e) => setExpress(e.target.checked)} data-testid="assessment-express-toggle" />
              <span
                aria-hidden
                className="relative h-5 w-9 shrink-0 rounded-full bg-hairline transition-colors peer-checked:bg-brand peer-focus-visible:outline-2 peer-focus-visible:outline-brand after:absolute after:top-0.5 after:left-0.5 after:size-4 after:rounded-full after:bg-card after:transition-transform peer-checked:after:translate-x-4"
              />
              <span className="font-semibold">{T.expressShort}</span>
              <Num className="text-12 text-muted">{T.expressMinutes}</Num>
            </label>
            {express && <p className="-mt-3 text-13 text-muted">{T.expressHint}</p>}
          </Panel>

          {put.isError && <ErrorLine error={put.error} data-testid="assessment-survey-error" />}
          {create.isError && <ErrorLine error={create.error} data-testid="assessment-start-error" />}
          {savedNote}
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <Button size="lg" loading={create.isPending} disabled={startDisabled} onClick={onStart} data-testid="assessment-start">
              {startLabel}
            </Button>
            <Button variant="outline" size="lg" loading={put.isPending && !create.isPending} disabled={busy} onClick={() => submit(false)} data-testid="assessment-save">
              {T.save}
            </Button>
            <Button
              variant="ghost"
              size="lg"
              disabled={busy}
              onClick={() => {
                setDone(false);
                setStep(1);
              }}
              data-testid="assessment-back"
              className="sm:ml-auto"
            >
              {T.back}
            </Button>
          </div>
          {lockUntil && !lowerGrade && <p className="text-13 text-muted">{T.until(dateShort(lockUntil))}</p>}
          <p className="text-12 text-muted">{T.historyHint}</p>
        </div>
      )}
    </Page>
  );
}
