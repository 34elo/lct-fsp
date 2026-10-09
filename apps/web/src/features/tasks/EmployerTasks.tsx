import { PAGE } from "@/shared/lib/page";
import { Gloss } from "@/shared/Gloss";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { Button, EmptyState, ErrorState, Skeleton, buttonVariants } from "@fsp/ui";

import {
  getListSubmissionsEmployerTasksTaskIdSubmissionsGetQueryKey,
  getListTasksEmployerTasksGetQueryKey,
  useCloseTaskEmployerTasksTaskIdClosePost,
  useListSubmissionsEmployerTasksTaskIdSubmissionsGet,
  useListTasksEmployerTasksGet,
  usePublishTaskEmployerTasksTaskIdPublishPost,
  useScoreSubmissionEmployerTasksTaskIdSubmissionsSubmissionIdScorePut,
} from "@/api/endpoints/assessment/assessment";
import type { AppAssessmentTasksRouterTaskOut as TaskOut, SubmissionOut } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { pct } from "./model";
import { TASKS_TEXT as T } from "./text";

function answerText(a: unknown): string {
  if (a == null) return "";
  return typeof a === "string" ? a : JSON.stringify(a);
}

function Rubric({ taskId, sub, rubric }: { taskId: string; sub: SubmissionOut; rubric: string[] }) {
  const qc = useQueryClient();
  const [marks, setMarks] = useState<boolean[]>(sub.rubric_marks ?? rubric.map(() => false));
  const score = useScoreSubmissionEmployerTasksTaskIdSubmissionsSubmissionIdScorePut({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: getListSubmissionsEmployerTasksTaskIdSubmissionsGetQueryKey(taskId) });
        void qc.invalidateQueries({ queryKey: getListTasksEmployerTasksGetQueryKey() });
      },
    },
  });
  return (
    <fieldset className="grid gap-2" data-testid="tasks-rubric">
      <legend className="text-12 font-semibold text-muted">{T.rubricTitle}</legend>
      {rubric.map((r, i) => (
        <label key={i} className="flex min-h-10 items-center gap-2 text-14">
          <input type="checkbox" className="accent-brand" checked={marks[i] ?? false} onChange={(e) => setMarks(marks.map((m, j) => (j === i ? e.target.checked : m)))} />
          {r}
        </label>
      ))}
      {score.isError && <ErrorNote>{T.scoreError}</ErrorNote>}
      <Button size="sm" className="justify-self-start" loading={score.isPending} onClick={() => score.mutate({ taskId, submissionId: sub.id, data: { marks } })} data-testid="tasks-score-save">
        {score.isPending ? T.savingScore : T.saveScore}
      </Button>
    </fieldset>
  );
}

function Submissions({ task }: { task: TaskOut }) {
  const q = useListSubmissionsEmployerTasksTaskIdSubmissionsGet(task.id);
  const subs = (q.data?.status === 200 ? q.data.data : []) as SubmissionOut[];
  if (q.isPending) return <Skeleton role="status" aria-label="Загрузка" className="h-16" />;
  if (q.isError) return <ErrorState title={T.subsError} onRetry={() => void q.refetch()} />;
  if (subs.length === 0) return <p className="text-14 text-muted">{T.subsEmpty}</p>;
  return (
    <ul className="grid gap-2">
      {subs.map((s) => (
        <li key={s.id} data-testid="tasks-submission" className="grid gap-2 rounded-xl border border-hairline p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-14 font-semibold">{T.anon(s.pseudo_id)} · {T.roundOf(s.round)}</span>
            <span className="text-12 text-muted">
              {s.score == null ? T.notScored : s.scored_by === "employer" ? T.scoreEmployer(pct(s.score)) : T.scoreAuto(pct(s.score))}
            </span>
          </div>
          <p className="whitespace-pre-wrap break-words text-14"><span className="text-muted">{T.answerOf}: </span>{answerText(s.answer)}</p>
          {task.kind === "open" && task.rubric && task.rubric.length > 0 && <Rubric taskId={task.id} sub={s} rubric={task.rubric} />}
          <Link to={s.invite_url} className={buttonVariants({ size: "sm", variant: "outline" }) + " justify-self-start"} data-testid="tasks-invite">
            {T.invite}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function TaskRow({ t }: { t: TaskOut }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: getListTasksEmployerTasksGetQueryKey() });
  const publish = usePublishTaskEmployerTasksTaskIdPublishPost({ mutation: { onSuccess: refresh } });
  const close = useCloseTaskEmployerTasksTaskIdClosePost({ mutation: { onSuccess: refresh } });
  const failed = publish.isError || close.isError;
  return (
    <li data-testid="tasks-employer-row" className="flex flex-col gap-3 rounded-2xl border border-hairline bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="break-words font-mono text-16 font-semibold">{t.title}</h2>
          <p className="text-13 text-muted">
            {T.category(roleLabel(t.profession), GRADE_LABEL[t.grade] ?? t.grade)} · {T.kinds[t.kind] ?? t.kind} · {T.roundOf(t.round)}
          </p>
        </div>
        <span className="rounded-full border border-hairline px-2.5 py-0.5 text-12 font-semibold text-muted" data-testid="tasks-employer-status">{T.empStatus[t.status] ?? t.status}</span>
      </div>
      <p className="text-13 text-muted">{T.counters(t.submissions ?? 0, t.scored ?? 0)}</p>
      {publish.data?.status === 200 && publish.data.data.delivered === false && <p role="status" className="text-13 text-muted">{T.publishedAgain}</p>}
      {failed && <ErrorNote>{T.actionError}</ErrorNote>}
      <div className="flex flex-wrap gap-2">
        {t.status === "draft" && (
          <Button size="sm" loading={publish.isPending} onClick={() => publish.mutate({ taskId: t.id })} data-testid="tasks-publish">{T.publish}</Button>
        )}
        {t.status === "open" && (
          <>
            <Button size="sm" variant="outline" loading={publish.isPending} onClick={() => publish.mutate({ taskId: t.id })} data-testid="tasks-republish">{T.publish}</Button>
            <Button size="sm" variant="outline" loading={close.isPending} onClick={() => close.mutate({ taskId: t.id })} data-testid="tasks-close">{T.close}</Button>
          </>
        )}
        {t.status !== "draft" && (
          <Button size="sm" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)} data-testid="tasks-toggle">{open ? T.hideAnswers : T.showAnswers}</Button>
        )}
      </div>
      {open && <Submissions task={t} />}
    </li>
  );
}

/** Задания компании (Z1, работодатель): статусы, ответы, оценка рубрикой, «Пригласить». */
export default function EmployerTasks() {
  const q = useListTasksEmployerTasksGet();
  const all = (q.data?.status === 200 ? q.data.data : []) as TaskOut[];
  return (
    <main className={PAGE.normal} data-testid="tasks-employer-page">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="font-mono text-24 font-semibold">
            <Gloss k="employerTask">{T.empTitle}</Gloss>
          </h1>
          <p className="text-14 text-muted">{T.empLead}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/employer/families/guide" className={buttonVariants({ variant: "ghost" })} data-testid="tasks-howto">{T.howTo}</Link>
          <Link to="/employer/families/new" className={buttonVariants({ variant: "outline" })}>{T.toConstructor}</Link>
        </div>
      </header>
      {q.isPending && <Skeleton role="status" aria-label="Загрузка" className="h-48" />}
      {q.isError && <ErrorState title={T.empLoadError} onRetry={() => void q.refetch()} />}
      {q.isSuccess && all.length === 0 && <EmptyState title={T.empEmpty} description={T.empEmptyHint} action={<Link to="/employer/families/guide" className={buttonVariants()} data-testid="tasks-empty-guide">{T.howTo}</Link>} />}
      {all.length > 0 && <ul className="grid gap-3">{all.map((t) => <TaskRow key={t.id} t={t} />)}</ul>}
    </main>
  );
}
