import { Button, Chips, cn, Field, FieldInput, GradeTag, H1, Input, Lbl, Num, Panel, Skeleton, SkillTag, StatusTag } from "@fsp/ui";
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
import { addStack, isFuture, salaryError } from "./model";
import { FORMAT_OPTIONS, GRADE, GRADE_CARDS, T, dateShort } from "./text";
import { ErrorLine, LoadError, Page } from "./ui";

const isGrade = (g: string | null | undefined): g is TestGrade => GRADE_CARDS.some((c) => c.grade === g);
const GRADE_ORDER: TestGrade[] = ["junior", "middle", "senior"];

/** Сегмент `.sg`: радио-группа в виде переключателя; `lockedValue` — грейд в кулдауне (контур вместо заливки). */
function Segmented<V extends string>({
  label,
  value,
  options,
  onChange,
  testid,
  lockedValue,
}: {
  label: string;
  value: V | "";
  options: { value: V; label: string }[];
  onChange: (v: V) => void;
  testid: (v: V) => string;
  lockedValue?: V | "";
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-0.5 rounded-lg bg-tint-50 p-0.5">
      {options.map((o) => {
        const on = value === o.value;
        const locked = on && lockedValue === o.value;
        return (
          <label
            key={o.value}
            className={cn(
              "inline-flex min-h-9 cursor-pointer items-center rounded-md px-3.5 text-14 font-semibold has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand",
              on && !locked && "bg-brand text-on-brand",
              locked && "bg-transparent text-brand-fg shadow-[inset_0_0_0_1px_var(--brand)]",
              !on && "text-muted hover:text-ink",
            )}
          >
            <input type="radio" className="sr-only" checked={on} onChange={() => onChange(o.value)} data-testid={testid(o.value)} />
            {o.label}
          </label>
        );
      })}
    </div>
  );
}

function Fld({ label, resume, tid, children }: { label: string; resume?: boolean; tid?: string; children: React.ReactNode }) {
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

const money = (v: string) => `${Number(v).toLocaleString("ru-RU")} ₽`;

/** S1: опрос и выбор грейда (макет v2_me-assessment). Одна форма на всех ширинах; справа (на 375 — снизу) «Заявляешь» и кнопка старта. */
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

  const [profession, setProfession] = useState("");
  const [stack, setStack] = useState<string[]>([]);
  const [stackDraft, setStackDraft] = useState("");
  const [formats, setFormats] = useState<WorkFormat[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [grade, setGrade] = useState<TestGrade | "">("");
  const [express, setExpress] = useState(params.get("mode") === "express"); // E32-4a: вход жюри
  const [touched, setTouched] = useState(false);
  const [done, setDone] = useState(false);
  const [picking, setPicking] = useState(false);
  const [hint, setHint] = useState(false);

  // Предзаполнение один раз: опрос или черновик из анкеты, затем параметры ссылки из навигатора.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    if (filled || !survey) return;
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
    industry: survey?.industry ?? null, // ADR-025 п.4: отрасль не спрашиваем, прежнее значение сохраняем
    profession,
    stack,
    formats,
    salary_from: from ? Number(from) : null,
    salary_to: to ? Number(to) : null,
    declared_grade: g || null,
  });

  const valid = !!profession && !rangeBad;

  async function submit(start: boolean, as?: TestGrade) {
    setTouched(true);
    setDone(false);
    create.reset();
    const g = as ?? grade;
    if (as) setGrade(as);
    if (!valid || (start && !g)) return;
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

  const profTitle = professions.find((p) => p.slug === profession)?.title ?? profession;
  const resume = !!survey?.prefilled;
  const showEmpty = !!survey && !profession && !picking;

  const startLabel = lockUntil && lowerGrade ? T.startLower(GRADE[lowerGrade] ?? lowerGrade) : T.startTest;
  const startDisabled = busy || (!!lockUntil && !lowerGrade);
  const onStart = () => (lockUntil && lowerGrade ? submit(true, lowerGrade) : submit(true));

  return (
    <Page wide>
      <div className="flex items-center justify-between gap-3">
        <H1 className="max-md:text-[22px]">{T.surveyHeading}</H1>
        <Link to="/me/assessment/history" className="text-14 font-semibold text-brand-fg underline" data-testid="assessment-history-link">
          {T.historyLink}
        </Link>
      </div>

      {sq.isPending || pq.isPending ? (
        <div role="status" aria-label={T.loading} className="grid gap-4 md:grid-cols-2">
          {[0, 1].map((i) => (
            <Panel key={i} className="flex flex-col gap-2.5">
              <Skeleton className="h-4 w-2/5" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3 w-3/4" />
            </Panel>
          ))}
        </div>
      ) : sq.isError || pq.isError ? (
        <LoadError error={sq.error ?? pq.error} onRetry={() => (sq.isError ? sq.refetch() : pq.refetch())} />
      ) : showEmpty ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-hairline p-10 text-center" data-testid="assessment-empty">
          <b className="font-mono text-16">{T.noProfession}</b>
          <Button size="lg" onClick={() => setPicking(true)} data-testid="assessment-pick">
            {T.pickProfession}
          </Button>
        </div>
      ) : (
        <div className="grid items-start gap-4 md:grid-cols-12">
          <div className="flex flex-col gap-3 md:col-span-7">
            {lockUntil && (
              <Panel className="flex items-center gap-3 bg-tint-50" data-testid="assessment-cooldown">
                <Lbl>{T.nextAttempt(GRADE[grade] ?? grade)}</Lbl>
                <Num className="ml-auto text-18" data-testid="assessment-cooldown-date">
                  {dateShort(lockUntil)}
                </Num>
              </Panel>
            )}

            <Panel className="flex flex-col gap-[18px]" data-testid="assessment-survey">
              <Fld label={T.direction} resume={resume} tid="assessment-prefilled">
                <Segmented
                  label={T.profession}
                  value={profession}
                  options={professions.map((p) => ({ value: p.slug, label: p.title }))}
                  onChange={setProfession}
                  testid={(v) => `assessment-profession-${v}`}
                />
                {touched && !profession && (
                  <p role="alert" className="text-13 text-error">
                    {T.needProfession}
                  </p>
                )}
              </Fld>

              <Fld label={T.stack} resume={resume}>
                <Chips data-testid="assessment-stack">
                  {stack.map((s) => (
                    <button key={s} type="button" aria-label={T.stackRemove(s)} onClick={() => setStack(stack.filter((x) => x !== s))} className="rounded-sm">
                      <SkillTag
                        name={
                          <>
                            {s} <span aria-hidden>×</span>
                          </>
                        }
                        state="claimed"
                      />
                    </button>
                  ))}
                </Chips>
                <form
                  className="flex gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setStack(addStack(stack, stackDraft));
                    setStackDraft("");
                  }}
                >
                  <Input aria-label={T.stackAdd} placeholder={T.stackAdd} value={stackDraft} onChange={(e) => setStackDraft(e.target.value)} data-testid="assessment-stack-input" />
                  <Button type="submit" variant="outline" data-testid="assessment-stack-add">
                    {T.stackAddBtn}
                  </Button>
                </form>
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
                          "min-h-8 rounded-sm border px-2.5 font-mono text-12 font-medium",
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
                <div className="grid grid-cols-2 gap-3">
                  <Field label={T.salaryFrom} error={rangeBad ? T.invalidRange : undefined}>
                    <FieldInput type="number" inputMode="numeric" min={0} value={from} onChange={(e) => setFrom(e.target.value)} data-testid="assessment-salary-from" />
                  </Field>
                  <Field label={T.salaryTo}>
                    <FieldInput type="number" inputMode="numeric" min={0} value={to} onChange={(e) => setTo(e.target.value)} data-testid="assessment-salary-to" />
                  </Field>
                </div>
              </Fld>

              <Fld label={T.gradeLabel}>
                <div className="flex items-center gap-2">
                  <Segmented
                    label={T.gradeQ}
                    value={grade}
                    options={GRADE_CARDS.map((c) => ({ value: c.grade, label: GRADE[c.grade] ?? c.grade }))}
                    onChange={setGrade}
                    testid={(v) => `assessment-grade-${v}`}
                    lockedValue={lockUntil ? grade : ""}
                  />
                  <button
                    type="button"
                    aria-label={T.gradeHelp}
                    aria-expanded={hint}
                    onClick={() => setHint(!hint)}
                    className="h-6 rounded-xl bg-tint-100 px-1.5 font-mono text-12 font-semibold text-brand-fg"
                    data-testid="assessment-grade-help"
                  >
                    ?
                  </button>
                </div>
                {hint && (
                  <div className="flex flex-col gap-1 rounded-lg bg-tint-50 p-3 text-13 text-muted" data-testid="assessment-grade-hint">
                    {GRADE_CARDS.map((c) => (
                      <p key={c.grade}>
                        <b className="text-ink">{GRADE[c.grade]}</b> · {T.gradeMinutes(c.minutes)}. {c.lead}
                      </p>
                    ))}
                    <p>{T.gradeHint}</p>
                  </div>
                )}
                {touched && !grade && (
                  <p role="alert" className="text-13 text-error" data-testid="assessment-need-grade">
                    {T.needGrade}
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
              {express && <p className="text-13 text-muted">{T.expressHint}</p>}
            </Panel>

            {put.isError && <ErrorLine error={put.error} data-testid="assessment-survey-error" />}
            {create.isError && <ErrorLine error={create.error} data-testid="assessment-start-error" />}
            {done && (
              <p role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-success-bg px-3 py-2 text-14 text-success" data-testid="assessment-saved">
                <span>
                  {T.saved}. {T.savedLater}
                </span>
                <Link to="/me" className="font-semibold underline" data-testid="assessment-later">
                  {T.toHome}
                </Link>
              </p>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" loading={put.isPending && !create.isPending} disabled={busy} onClick={() => submit(false)} data-testid="assessment-save">
                {T.save}
              </Button>
              <span className="text-12 text-muted">{T.historyHint}</span>
            </div>
          </div>

          <div className="md:col-span-5">
            <Panel className="flex flex-col gap-3 max-md:border-0 max-md:bg-transparent max-md:p-0">
              <Lbl className="max-md:hidden">{T.declares}</Lbl>
              <div className="flex flex-wrap items-center gap-2 max-md:hidden">
                <GradeTag claimed>
                  {grade ? GRADE[grade] : "—"} · {profTitle || "—"}
                </GradeTag>
                <StatusTag state="claimed">{T.notConfirmed}</StatusTag>
              </div>
              <Chips className="max-md:hidden">
                {stack.map((s) => (
                  <SkillTag key={s} name={s} state="claimed" />
                ))}
              </Chips>
              <div className="text-13 text-muted max-md:hidden" data-testid="assessment-summary">
                {T.expectations} <Num className="text-ink">{from ? `${T.salaryFromShort} ${money(from)}` : "—"}</Num>
                {formats.length > 0 && (
                  <>
                    <br />
                    {formats.map((f) => FORMAT_OPTIONS.find((o) => o.value === f)?.label.toLowerCase()).join(" · ")}
                  </>
                )}
              </div>
              <Button size="lg" className="w-full" loading={create.isPending} disabled={startDisabled} onClick={onStart} data-testid="assessment-start">
                {startLabel}
              </Button>
              {lockUntil && !lowerGrade && <p className="text-13 text-muted">{T.until(dateShort(lockUntil))}</p>}
            </Panel>
          </div>
        </div>
      )}
    </Page>
  );
}
