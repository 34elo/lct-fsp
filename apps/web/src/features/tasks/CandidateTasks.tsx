import { PAGE } from "@/shared/lib/page";
import { Gloss } from "@/shared/Gloss";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, EmptyState, ErrorState, Skeleton, buttonVariants } from "@fsp/ui";

import {
  getMyTasksAssessmentTasksGetQueryKey,
  getMyTaskAssessmentTasksTaskIdGetQueryKey,
  useAnswerTaskAssessmentTasksTaskIdAnswerPost,
  useMyTaskAssessmentTasksTaskIdGet,
  useMyTasksAssessmentTasksGet,
} from "@/api/endpoints/assessment/assessment";
import type { CandidateTaskDetail, CandidateTaskOut } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { dateOnly } from "@/features/offers/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { AnswerField } from "./AnswerForm";
import { candStatus, initialAnswer, inTab, isClosed, isReady, pct, toAnswer, type AnswerState, type TaskItem } from "./model";
import { TASKS_TEXT as T } from "./text";

const category = (t: { profession: string; grade: string }) => `${GRADE_LABEL[t.grade] ?? t.grade} · ${roleLabel(t.profession)}`;

function statusText(t: CandidateTaskOut): string {
  const s = candStatus(t);
  if (s === "scored") return T.statusScored(pct(t.score ?? 0));
  return { new: T.statusNew, accepted: T.statusAccepted, waiting: T.statusWaiting, closed: T.statusClosed, scored: "" }[s];
}

function TaskCard({ t }: { t: CandidateTaskOut }) {
  const [, setParams] = useSearchParams();
  const s = candStatus(t);
  return (
    <li data-testid="tasks-card" className="flex flex-col gap-2 rounded-2xl border border-hairline bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="rounded-full border border-hairline px-2.5 py-0.5 text-12 font-semibold text-muted" data-testid="tasks-status">{statusText(t)}</span>
        {t.answer_until && <span className="text-12 text-muted">{T.until(dateOnly(t.answer_until))}</span>}
      </div>
      <h2 className="break-words font-mono text-16 font-semibold">{t.title}</h2>
      <p className="text-13 text-muted">{category(t)} · {T.kinds[t.kind] ?? t.kind}</p>
      <Button size="lg" variant={s === "new" ? "primary" : "outline"} onClick={() => setParams({ task: t.id })} data-testid="tasks-open">
        {s === "new" ? T.solve : T.view}
      </Button>
    </li>
  );
}

function Detail({ id, onBack }: { id: string; onBack: () => void }) {
  const qc = useQueryClient();
  const q = useMyTaskAssessmentTasksTaskIdGet(id);
  const d = (q.data?.status === 200 ? q.data.data : null) as CandidateTaskDetail | null;
  const [value, setValue] = useState<AnswerState | undefined>(undefined);
  const answer = useAnswerTaskAssessmentTasksTaskIdAnswerPost({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: getMyTasksAssessmentTasksGetQueryKey() });
        void qc.invalidateQueries({ queryKey: getMyTaskAssessmentTasksTaskIdGetQueryKey(id) });
      },
    },
  });
  const back = (
    <Button variant="ghost" onClick={onBack} data-testid="tasks-back">{T.back}</Button>
  );
  if (q.isPending) return <Skeleton role="status" aria-label="Загрузка" className="h-64" />;
  if (!d) return <ErrorState title={T.detailError} onRetry={() => void q.refetch()} />;
  const item = d.item as TaskItem;
  const val = value ?? initialAnswer(item);
  const closed = !d.submitted && isClosed(d);
  const waiting = d.submitted && d.submission_score == null && d.score == null;
  const score = d.submission_score ?? d.score;
  const err = answer.error as { status?: number } | null;
  return (
    <section className="flex flex-col gap-4" data-testid="tasks-detail">
      {back}
      <div className="flex flex-col gap-2 rounded-2xl border border-hairline bg-card p-4">
        <p className="font-mono text-12 text-muted">{T.round(d.round)}</p>
        <h1 className="break-words font-mono text-20 font-semibold">{d.title}</h1>
        <p className="text-13 text-muted">
          {category(d)}{d.answer_until ? ` · ${T.until(dateOnly(d.answer_until))}` : ""} · {T.kinds[d.kind] ?? d.kind}
        </p>
        {item.stem && <p className="whitespace-pre-wrap break-words text-14" data-testid="tasks-stem">{item.stem}</p>}
      </div>
      {closed ? (
        <EmptyState title={T.closedTitle} description={T.closedText(d.answer_until ? dateOnly(d.answer_until) : "")} action={<Button variant="outline" onClick={onBack}>{T.back}</Button>} />
      ) : (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (d.submitted || !isReady(item, val)) return;
            answer.mutate({ taskId: id, data: { answer: toAnswer(item, val) } });
          }}
        >
          <AnswerField id={`task-${id}`} item={item} value={val} onChange={setValue} disabled={!!d.submitted} />
          {d.submitted ? (
            <p role="status" className="rounded-lg bg-tint-50 px-3 py-2 text-14" data-testid="tasks-result">
              {T.accepted}. {waiting ? T.waitingScore : score != null ? T.yourScore(pct(score)) : ""}
            </p>
          ) : (
            <>
              <p className="text-12 text-muted">{T.answerHint}</p>
              {answer.isError && <ErrorNote data-testid="tasks-error">{err?.status === 409 || err?.status === 410 ? T.roundClosedError : T.answerError}</ErrorNote>}
              <Button type="submit" size="lg" loading={answer.isPending} disabled={!isReady(item, val)} data-testid="tasks-submit">
                {answer.isPending ? T.submitting : T.submit}
              </Button>
            </>
          )}
        </form>
      )}
    </section>
  );
}

/** Регулярные задания (Z1, кандидат): список, ответ, статусы. Ответ не идёт в грейд. */
export default function CandidateTasks() {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<"open" | "mine">("open");
  const q = useMyTasksAssessmentTasksGet();
  const all = (q.data?.status === 200 ? q.data.data : []) as CandidateTaskOut[];
  const taskId = params.get("task");
  const shown = all.filter((t) => inTab(t, tab));
  return (
    <main className={PAGE.normal} data-testid="tasks-page">
      {taskId ? (
        <Detail id={taskId} onBack={() => setParams({})} />
      ) : (
        <>
          <header>
            <h1 className="font-mono text-24 font-semibold">
              <Gloss k="regularTasks">{T.candTitle}</Gloss>
            </h1>
            <p className="text-14 text-muted">{T.candLead}</p>
          </header>
          {q.isPending && <Skeleton role="status" aria-label={T.loading} className="h-48" />}
          {q.isError && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
          {q.isSuccess && all.length === 0 && (
            <div data-testid="tasks-empty">
              <EmptyState
                title={T.emptyTitle}
                description={T.emptyHint}
                action={
                  <div className="flex flex-wrap justify-center gap-2">
                    <Link to="/me/assessment" className={buttonVariants({ variant: "outline" })}>{T.toAssessment}</Link>
                    <Link to="/consents" className={buttonVariants({ variant: "outline" })}>{T.toConsents}</Link>
                  </div>
                }
              />
            </div>
          )}
          {all.length > 0 && (
            <>
              <div role="group" aria-label={T.filterLabel} className="flex gap-2">
                {(Object.keys(T.tabs) as ("open" | "mine")[]).map((k) => (
                  <button
                    key={k}
                    type="button"
                    aria-pressed={tab === k}
                    data-testid={`tasks-tab-${k}`}
                    onClick={() => setTab(k)}
                    className={`h-9 rounded-lg border px-3 font-mono text-13 ${tab === k ? "border-brand bg-tint-50 text-brand-fg" : "border-hairline text-muted hover:bg-tint-50"}`}
                  >
                    {T.tabs[k]} ({all.filter((t) => inTab(t, k)).length})
                  </button>
                ))}
              </div>
              {shown.length === 0 ? <p className="text-14 text-muted">{tab === "mine" ? T.emptyMine : T.emptyTitle}</p> : <ul className="grid gap-3 md:grid-cols-2">{shown.map((t) => <TaskCard key={t.id} t={t} />)}</ul>}
            </>
          )}
        </>
      )}
    </main>
  );
}
