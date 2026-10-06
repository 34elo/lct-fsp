import { Button, Card, Progress, SectionLabel, Skeleton } from "@fsp/ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import {
  useAnswerAssessmentAttemptsAttemptIdAnswersPost,
  useGetAttemptAssessmentAttemptsAttemptIdGet,
  useNextItemAssessmentAttemptsAttemptIdNextGet,
} from "@/api/endpoints/assessment/assessment";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { NextOut } from "@/api/model";
import { cn } from "@/shared/lib/cn";
import { chainSteps, formatClock, initialAnswer, isAnswered, toPayload, type AnswerValue, type TestItem } from "./model";
import { Question } from "./Question";
import { GRADE, KIND_LABEL, T } from "./text";
import { ErrorLine, LoadError, Page, retryServerOnly } from "./ui";

type Telemetry = { away_ms: number[]; pastes: number };

/** Уход со вкладки и вставки (assessment.md §8): считаем, не наказываем. */
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

function Clock({ left, limit }: { left: number | null; limit: number | null | undefined }) {
  if (left == null || !limit) return null;
  const low = left <= 10;
  return (
    <div
      role="timer"
      aria-label={T.timeLeft}
      data-testid="assessment-timer"
      className={cn("grid size-16 place-items-center rounded-full border-4 font-mono text-14 font-semibold", low ? "border-warning-border text-warning-fg" : "border-tint-200")}
    >
      {formatClock(left)}
    </div>
  );
}

/** Одно задание: свои состояние, таймер и телеметрия. Ответ уходит один раз. */
function ItemRunner({
  item,
  num,
  pending,
  error,
  onSubmit,
}: {
  item: NextOut;
  num: number;
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
  const kindLabel = KIND_LABEL[kind] ?? kind;

  return (
    <Card className="flex flex-col gap-4 p-5" data-testid="assessment-item" data-kind={kind}>
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-18 font-semibold">
            {T.taskN(num)} · {kindLabel}
          </h2>
        </div>
        <Clock left={clock.left} limit={item.time_limit_s} />
      </header>

      {kind === "chain" && (
        <div className="flex flex-col gap-3" data-testid="assessment-chain">
          <p className="whitespace-pre-line text-16">{item.stem}</p>
          <p className="text-12 text-muted">{T.chainLead}</p>
          <ol className="flex items-center gap-1" aria-label={T.chainStep(stepIdx + 1, steps.length)}>
            {steps.map((_, i) => (
              <li
                key={i}
                aria-current={i === stepIdx ? "step" : undefined}
                className={cn("h-1.5 flex-1 rounded-full", i < stepIdx ? "bg-brand-mid" : i === stepIdx ? "bg-brand" : "bg-tint-100")}
              />
            ))}
          </ol>
          <SectionLabel data-testid="assessment-chain-step">{T.chainStep(stepIdx + 1, steps.length)}</SectionLabel>
        </div>
      )}

      <Question key={`${item.response_id}-${stepIdx}`} item={shown} value={value} onChange={setValue} disabled={pending || sent.current} idPrefix={`q${stepIdx}`} />

      {expired && (
        <p role="status" className="text-13 text-muted" data-testid="assessment-timeup">
          {T.timeUp}
        </p>
      )}
      {!!error && <ErrorLine error={error} data-testid="assessment-answer-error" />}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          loading={pending}
          disabled={!ready || pending}
          onClick={() => answerNow(false)}
          data-testid="assessment-next"
        >
          {lastStep ? T.answer : T.chainNext}
        </Button>
        <Button variant="ghost" disabled={pending} onClick={() => answerNow(true)} data-testid="assessment-skip">
          {T.dontKnow}
        </Button>
        {!!error && sent.current && (
          <Button variant="outline" disabled={pending} onClick={() => finish(lastSent.current)} data-testid="assessment-resend">
            {T.retry}
          </Button>
        )}
      </div>
      <p className="text-12 text-muted">{T.noBack}</p>
    </Card>
  );
}

/** S2: тест по одному заданию. Правильность не показываем; цепочка идёт пошагово. */
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
  const pct = target > 0 ? Math.min(100, Math.round((answered / target) * 100)) : 0;

  return (
    <Page wide>
      <header className="flex flex-col gap-2">
        <h1 className="font-mono text-2xl font-semibold" data-testid="assessment-title">
          {T.testTitle}
          {attempt && ` · ${title} ${GRADE[attempt.declared_grade] ?? attempt.declared_grade}`}
        </h1>
        <div className="flex flex-col gap-1" data-testid="assessment-progress">
          <Progress value={pct} aria-label={T.progressLabel} className="h-1.5" />
          <p className="text-12 text-muted">
            <span data-testid="assessment-answered">{T.answered(answered)}</span> · {T.progressHint}
          </p>
        </div>
      </header>

      <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
        <div>
          {nq.isPending || (nq.isFetching && !ans.isPending) ? (
            <div role="status" aria-label={T.loading} className="flex flex-col gap-3">
              <Skeleton className="h-16" />
              <Skeleton className="h-48" />
            </div>
          ) : nq.isError || aq.isError ? (
            <LoadError error={nq.error ?? aq.error} onRetry={() => (nq.isError ? nq.refetch() : aq.refetch())} />
          ) : item?.done || !item?.response_id ? (
            <p role="status" className="text-14 text-muted">
              {T.finishing}
            </p>
          ) : (
            <ItemRunner
              key={item.response_id}
              item={item}
              num={item.seq ?? answered + 1}
              pending={ans.isPending}
              error={ans.error}
              onSubmit={submit}
            />
          )}
        </div>

        <aside className="flex flex-col gap-3" aria-label={T.rules}>
          <Card className="flex flex-col gap-2 p-4">
            <SectionLabel>{T.rules}</SectionLabel>
            <ul className="flex list-disc flex-col gap-1 pl-4 text-13 text-muted">
              {T.rulesList.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Card>
          {attempt && (
            <Card className="flex flex-col gap-1 p-4 text-13">
              <SectionLabel>{T.declared}</SectionLabel>
              <p className="font-semibold">
                {GRADE[attempt.declared_grade] ?? attempt.declared_grade} · {title}
              </p>
              <p className="text-muted">{T.range}</p>
            </Card>
          )}
        </aside>
      </div>
    </Page>
  );
}
