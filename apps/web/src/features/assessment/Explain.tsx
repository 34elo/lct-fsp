import { Badge, Button, Card, SectionLabel } from "@fsp/ui";
import { useState } from "react";

import { useExplainAnswerAssessmentAttemptsAttemptIdResponsesResponseIdExplainPost } from "@/api/endpoints/assessment/assessment";
import type { ExplainInSelfReason } from "@/api/model";
import { missedAnswers, type AnswerRow } from "./model";
import { T } from "./text";
import { ErrorLine } from "./ui";

function Row({ attemptId, row }: { attemptId: string; row: AnswerRow }) {
  const explain = useExplainAnswerAssessmentAttemptsAttemptIdResponsesResponseIdExplainPost();
  const [mine, setMine] = useState("");
  const out = explain.data?.status === 200 ? explain.data.data : undefined;
  const ask = () =>
    explain.mutate({
      attemptId,
      responseId: row.responseId,
      data: mine ? { self_reason: mine as ExplainInSelfReason } : undefined,
    });

  return (
    <li className="flex flex-col gap-2 py-3" data-testid={`assessment-explain-${row.seq}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="font-semibold">{T.explainTask(row.seq)}</span>
        <span className="font-mono text-13 text-muted">{row.skill}</span>
        <label className="ml-auto flex items-center gap-2 text-13 text-muted">
          <span>{T.explainMyReason}</span>
          <select
            value={mine}
            onChange={(e) => setMine(e.target.value)}
            className="h-9 rounded-lg border border-hairline bg-card px-2 text-14 text-ink"
            data-testid={`assessment-explain-self-${row.seq}`}
          >
            <option value="">{T.explainMyReasonNone}</option>
            {Object.entries(T.selfReasons).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <Button size="sm" variant="outline" loading={explain.isPending} onClick={ask} data-testid={`assessment-explain-ask-${row.seq}`}>
          {out ? T.explainRetry : T.explainAsk}
        </Button>
      </div>
      {explain.isError && <ErrorLine error={explain.error} data-testid={`assessment-explain-error-${row.seq}`} />}
      {out && (
        <div className="flex flex-col gap-2 rounded-lg bg-tint-50 p-3 text-14" role="status" data-testid={`assessment-explain-out-${row.seq}`}>
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-13 text-muted">{T.explainWhy}</span>
            <Badge variant="muted" data-testid={`assessment-explain-reason-${row.seq}`}>
              {out.reason.label}
            </Badge>
          </p>
          <p>{out.text}</p>
          {out.misconception && (
            <p className="text-13 text-muted">
              <strong>{T.explainMisconception}:</strong> {out.misconception.claim} <strong>{T.explainTruth}:</strong> {out.misconception.truth}
            </p>
          )}
          {out.self_reason_matches != null && <p className="text-13 text-muted">{out.self_reason_matches ? T.explainMatch : T.explainDiffer}</p>}
          <p className="text-12 text-muted">{out.source === "llm" ? T.explainSourceLlm : T.explainSourceTemplate}</p>
        </div>
      )}
    </li>
  );
}

/** «Объясни ответ» (E24-2): только после завершения попытки и только неверные ответы; ключей нет. */
export function ExplainAnswers({ attemptId, answers }: { attemptId: string; answers: unknown }) {
  const rows = missedAnswers(answers);
  if (rows.length === 0) return null;
  return (
    <section className="flex flex-col gap-2" aria-labelledby="assessment-explain" data-testid="assessment-explain">
      <SectionLabel id="assessment-explain">{T.explainTitle}</SectionLabel>
      <p className="text-13 text-muted">{T.explainLead}</p>
      <Card className="p-4">
        <ul className="divide-y divide-hairline">
          {rows.map((r) => (
            <Row key={r.responseId} attemptId={attemptId} row={r} />
          ))}
        </ul>
      </Card>
    </section>
  );
}
