import { PAGE } from "@/shared/lib/page";
import { Button, cn, EmptyState, H1, Lbl, Panel, Skeleton, TaskHeader } from "@fsp/ui";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";

import {
  useAnswerAssessmentAttemptsAttemptIdAnswersPost,
  useGetAttemptAssessmentAttemptsAttemptIdGet,
  useNextItemAssessmentAttemptsAttemptIdNextGet,
} from "@/api/endpoints/assessment/assessment";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { NextOut } from "@/api/model";
import { chainSteps, initialAnswer, isAnswered, toPayload, type AnswerValue, type TestItem } from "./model";
import { Question } from "./Question";
import { GRADE, KIND_LABEL, T } from "./text";
import { ErrorLine, LoadError, retryServerOnly } from "./ui";

type Telemetry = { away_ms: number[]; pastes: number };

/** Уход со вкладки и вставки: считаем, не наказываем. */
function useTelemetry() {
  const away = useRef<number[]>([]);
  const hiddenAt = useRef<number | null>(null);
  const pastes = useRef(0);
  useEffect(() => {
    const vis = () => {
      if (document.visibilityState === "hidden") hiddenAt.current = Date.now();
      else if (hiddenAt.current != null) {
        away.current.push(Date.now() - hiddenAt.current);
        hiddenAt.current = null;
      }
    };
    const paste = () => {
      pastes.current += 1;
    };
    document.addEventListener("visibilitychange", vis);
    document.addEventListener("paste", paste, true);
    return () => {
      document.removeEventListener("visibilitychange", vis);
      document.removeEventListener("paste", paste, true);
    };
  }, []);
  return useCallback((): Telemetry => {
    const open = hiddenAt.current != null ? [Date.now() - hiddenAt.current] : [];
    return { away_ms: [...away.current, ...open], pastes: pastes.current };
  }, []);
}

/** Обратный отсчёт от монтирования; не останавливается. `onExpire` вызывается один раз. */
function useCountdown(limit: number | null | undefined, onExpire: () => void) {
  const start = useRef(Date.now());
  const [left, setLeft] = useState<number | null>(limit ?? null);
  const fired = useRef(false);
  const cb = useRef(onExpire);
  cb.current = onExpire;
  useEffect(() => {
    if (!limit) return;
    const tick = () => {
      const rest = limit - (Date.now() - start.current) / 1000;
      setLeft(Math.max(0, rest));
      if (rest <= 0 && !fired.current) {
        fired.current = true;
        cb.current();
      }
    };
    tick();
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, [limit]);
  return { left, elapsedMs: () => Date.now() - start.current };
}

/** Одно задание: свои состояние, таймер и телеметрия. Ответ уходит один раз. */
function ItemRunner({
  item,
  num,
  total,
  rules,
  pending,
  error,
  onSubmit,
}: {
  item: NextOut;
  num: number;
  total: number;
  /** Правила теста: открываются по «?» в шапке. */
  rules: ReactNode;
  pending: boolean;
  error: unknown;
  onSubmit: (answer: unknown, rtMs: number, telemetry: Telemetry) => void;
}) {
  const kind = item.kind ?? "choice";
  const base: TestItem = { kind, stem: item.stem ?? "", options: item.options };
  const steps = kind === "chain" ? chainSteps(item.steps) : [];
  const current: TestItem = kind === "chain" ? (steps[0] ?? base) : base;

  const [stepIdx, setStepIdx] = useState(0);
  const [done, setDone] = useState<unknown[]>([]);
  const [value, setValue] = useState<AnswerValue>(() => initialAnswer(current));
  const [expired, setExpired] = useState(false);
  const sent = useRef(false);
  const telemetry = useTelemetry();

  const shown: TestItem = kind === "chain" ? (steps[stepIdx] ?? base) : base;

  const lastSent = useRef<unknown>(null);
  const latest = useRef<() => void>(() => {});
  const clock = useCountdown(item.time_limit_s, () => latest.current());
  const finish = (answer: unknown) => {
    sent.current = true;
    lastSent.current = answer;
    onSubmit(answer, clock.elapsedMs(), telemetry());
  };
  // Таймер зовёт через ref, чтобы видеть актуальные значения.
  latest.current = () => {
    if (sent.current) return;
    setExpired(true);
    if (kind === "chain") finish(isAnswered(shown, value) ? [...done, toPayload(shown, value)] : done);
    else finish(isAnswered(base, value) ? toPayload(base, value) : null);
  };

  const answerNow = (skip: boolean) => {
    if (sent.current) return;
    const payload = skip ? null : toPayload(shown, value);
    if (kind === "chain") {
      const all = [...done, payload];
      if (stepIdx + 1 < steps.length) {
        setDone(all);
        setStepIdx(stepIdx + 1);
        setValue(initialAnswer(steps[stepIdx + 1]!));
        return;
      }
      finish(all);
    } else {
      finish(payload);
    }
  };

  const lastStep = kind !== "chain" || stepIdx + 1 >= steps.length;
  const ready = isAnswered(shown, value);

  const [help, setHelp] = useState(false);

  return (
    <div className="flex flex-col gap-4" data-testid="assessment-item" data-kind={kind}>
      <TaskHeader
        index={num}
        total={Math.max(total, num)}
        upTo
        kindLabel={KIND_LABEL[kind]}
        secondsLeft={clock.left != null && item.time_limit_s ? Math.ceil(clock.left) : undefined}
        onHelp={() => setHelp((v) => !v)}
      />
      {help && rules}

      <Panel className="flex flex-col gap-4 p-4 md:p-[18px]">
        {kind === "chain" && (
          <div className="flex flex-col gap-3" data-testid="assessment-chain">
            <p className="m-0 whitespace-pre-line text-16">{item.stem}</p>
            <p className="m-0 text-12 text-muted">{T.chainLead}</p>
            <ol className="m-0 flex list-none items-center gap-1 p-0" aria-label={T.chainStep(stepIdx + 1, steps.length)}>
              {steps.map((_, i) => (
                <li
                  key={i}
                  aria-current={i === stepIdx ? "step" : undefined}
                  className={cn("h-1.5 flex-1 rounded-full", i < stepIdx ? "bg-brand-mid" : i === stepIdx ? "bg-brand" : "bg-tint-100")}
                />
              ))}
            </ol>
            <Lbl data-testid="assessment-chain-step">{T.chainStep(stepIdx + 1, steps.length)}</Lbl>
          </div>
        )}

        <Question key={`${item.response_id}-${stepIdx}`} item={shown} value={value} onChange={setValue} disabled={pending || sent.current} idPrefix={`q${stepIdx}`} />
      </Panel>

      {expired && (
        <p role="status" className="m-0 text-13 text-muted" data-testid="assessment-timeup">
          {T.timeUp}
        </p>
      )}
      {!!error && <ErrorLine error={error} data-testid="assessment-answer-error" />}

      <div className="flex flex-col gap-2 md:flex-row-reverse md:items-center md:justify-between">
        <Button
          size="lg"
          loading={pending}
          disabled={!ready || pending}
          onClick={() => answerNow(false)}
          data-testid="assessment-next"
          className="w-full md:w-auto"
        >
          {lastStep ? T.answer : T.chainNext}
        </Button>
        <div className="flex flex-col gap-2 md:flex-row md:items-center">
          <Button variant="outline" disabled={pending} onClick={() => answerNow(true)} data-testid="assessment-skip" className="w-full md:w-auto">
            {T.dontKnow}
          </Button>
          {!!error && sent.current && (
            <Button variant="outline" disabled={pending} onClick={() => finish(lastSent.current)} data-testid="assessment-resend">
              {T.retry}
            </Button>
          )}
        </div>
      </div>
      <p className="m-0 text-12 text-muted">{T.noBack}</p>
    </div>
  );
}

/** Тест по одному заданию. Правильность не показываем; цепочка идёт пошагово. */
export default function Attempt() {
  const { id = "" } = useParams();
  const nav = useNavigate();
  const aq = useGetAttemptAssessmentAttemptsAttemptIdGet(id, { query: { retry: retryServerOnly } });
  const nq = useNextItemAssessmentAttemptsAttemptIdNextGet(id, {
    query: { retry: retryServerOnly, staleTime: Infinity, gcTime: 0, refetchOnWindowFocus: false, refetchOnReconnect: false },
  });
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const ans = useAnswerAssessmentAttemptsAttemptIdAnswersPost();

  const attempt = aq.data?.status === 200 ? aq.data.data : undefined;
  const item = nq.data?.status === 200 ? nq.data.data : undefined;
  const professions = pq.data?.status === 200 ? pq.data.data.professions : [];
  const title = attempt ? (professions.find((p) => p.slug === attempt.profession)?.title ?? attempt.profession) : "";

  const toResult = () => nav(`/me/assessment/attempts/${id}/result`, { replace: true });

  useEffect(() => {
    if (item?.done) toResult();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item?.done]);

  if (attempt && attempt.status !== "active") return <Navigate to={`/me/assessment/attempts/${id}/result`} replace />;

  const submit = (answer: unknown, rtMs: number, telemetry: Telemetry) => {
    if (!item?.response_id) return;
    ans.mutate(
      { attemptId: id, data: { response_id: item.response_id, answer, rt_ms: rtMs, telemetry } },
      {
        onSuccess: async (r) => {
          if (r.status === 200 && r.data.done) return toResult();
          ans.reset();
          await Promise.all([nq.refetch(), aq.refetch()]);
        },
      },
    );
  };

  const answered = attempt?.answered ?? 0;
  const target = attempt?.target ?? 0;

  const rules = (
    <Panel className="flex flex-col gap-2" aria-label={T.rules}>
      <Lbl>{T.rules}</Lbl>
      <ul className="m-0 flex list-disc flex-col gap-1 pl-4 text-13 text-muted">
        {T.rulesList.map((r) => (
          <li key={r}>{r}</li>
        ))}
      </ul>
      {attempt && (
        <div className="flex flex-col gap-0.5 border-t border-hairline pt-2 text-13">
          <Lbl>{T.declared}</Lbl>
          <p className="m-0 font-semibold" data-testid="assessment-title">
            {title} · {GRADE[attempt.declared_grade] ?? attempt.declared_grade}
          </p>
        </div>
      )}
    </Panel>
  );

  const heading = <H1>{T.testTitle}</H1>;

  if (nq.isPending || (nq.isFetching && !ans.isPending))
    return (
      <div role="status" aria-label={T.loading} className="flex flex-col gap-4">
        <Skeleton className="h-7 w-48" />
        <div className="grid gap-4 md:grid-cols-2">
          {[0, 1].map((i) => (
            <Panel key={i} className="flex flex-col gap-3">
              <Skeleton className="h-4 w-2/5" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3" />
              <Skeleton className="h-3 w-3/4" />
            </Panel>
          ))}
        </div>
      </div>
    );

  if (nq.isError || aq.isError)
    return (
      <div className="flex flex-col gap-4">
        {heading}
        <LoadError error={nq.error ?? aq.error} onRetry={() => (nq.isError ? nq.refetch() : aq.refetch())} />
      </div>
    );

  if (item?.done)
    return (
      <p role="status" className="text-14 text-muted">
        {T.finishing}
      </p>
    );

  if (!item?.response_id)
    return (
      <div className="flex flex-col gap-4" data-testid="assessment-empty">
        {heading}
        <EmptyState
          title={T.noActiveTitle}
          action={
            <Link to="/me/assessment" className="inline-flex h-11 items-center rounded-lg bg-brand px-4 text-14 font-semibold text-on-brand">
              {T.takeTest}
            </Link>
          }
        />
      </div>
    );

  return (
    <div className={PAGE.narrow}>
      <ItemRunner
        key={item.response_id}
        item={item}
        num={item.seq ?? answered + 1}
        total={target}
        rules={rules}
        pending={ans.isPending}
        error={ans.error}
        onSubmit={submit}
      />
      {attempt && (
        <p className="m-0 text-12 text-muted" data-testid="assessment-range">
          {attempt.mode === "express" ? T.rangeExpress : T.range}
        </p>
      )}
    </div>
  );
}
