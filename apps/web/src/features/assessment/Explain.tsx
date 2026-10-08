import { Button, ErrorBlock, Num, Panel, PanelCap, Tag } from "@fsp/ui";
import { useState } from "react";

import { useExplainAnswerAssessmentAttemptsAttemptIdResponsesResponseIdExplainPost } from "@/api/endpoints/assessment/assessment";
import type { ExplainInSelfReason } from "@/api/model";
import { missedAnswers, type AnswerRow } from "./model";
import { T } from "./text";
import { ErrorLine } from "./ui";

/** Одна ошибка `.er`: навык, задание, «Объясни ответ»; после ответа — причина и сверка со своей версией. */
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
    <div className="border-t border-hairline pt-3.5 first:border-t-0 first:pt-0" data-testid={`assessment-explain-${row.seq}`}>
      <ErrorBlock
        skill={row.skill || "—"}
        title={T.explainTask(row.seq)}
        action={
          <Button
            size="sm"
            variant="link"
            className="ml-auto px-2 no-underline"
            loading={explain.isPending}
            onClick={ask}
            data-testid={`assessment-explain-ask-${row.seq}`}
          >
            {out ? T.explainRetry : T.explainShort}
          </Button>
        }
      >
        {explain.isError && <ErrorLine error={explain.error} data-testid={`assessment-explain-error-${row.seq}`} />}
        {out && (
          <div className="flex flex-col gap-2 rounded-lg bg-tint-50 p-3 text-14" role="status" data-testid={`assessment-explain-out-${row.seq}`}>
            <p className="flex flex-wrap items-center gap-2">
              <span className="text-13 text-muted">{T.explainWhy}</span>
              <Tag data-testid={`assessment-explain-reason-${row.seq}`}>{out.reason.label}</Tag>
            </p>
            <p>{out.text}</p>
            {out.misconception && (
              <p className="text-13 text-muted">
                <strong>{T.explainMisconception}:</strong> {out.misconception.claim} <strong>{T.explainTruth}:</strong> {out.misconception.truth}
              </p>
            )}
            {out.self_reason_matches != null && <p className="text-13 text-muted">{out.self_reason_matches ? T.explainMatch : T.explainDiffer}</p>}
            <label className="flex flex-wrap items-center gap-2 text-13 text-muted">
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
            <p className="text-12 text-muted">{out.source === "llm" ? T.explainSourceLlm : T.explainSourceTemplate}</p>
          </div>
        )}
      </ErrorBlock>
    </div>
  );
}

/**
 * Ошибки (E24-2, макет v2): задания, где набрано не всё, с «Объясни ответ».
 * Только после завершения попытки; ключей и правильных ответов не показываем.
 */
export function ExplainAnswers({ attemptId, answers, className }: { attemptId: string; answers: unknown; className?: string }) {
  const rows = missedAnswers(answers);
  return (
    <Panel className={className} aria-labelledby="assessment-explain-title" data-testid="assessment-explain">
      <PanelCap
        title={
          <h2 id="assessment-explain-title" className="m-0 font-mono text-16 leading-[1.3] font-semibold">
            {T.errorsTitle}
          </h2>
        }
        aside={<Num className="text-12">{rows.length}</Num>}
      />
      {rows.length === 0 ? (
        <p className="text-14 text-muted" data-testid="assessment-explain-empty">
          {T.noErrors}
        </p>
      ) : (
        <>
          <p className="mb-2 text-13 text-muted">{T.explainLead}</p>
          <div>
            {rows.map((r) => (
              <Row key={r.responseId} attemptId={attemptId} row={r} />
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}
