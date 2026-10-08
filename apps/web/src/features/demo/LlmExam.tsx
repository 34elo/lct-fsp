import { PAGE } from "@/shared/lib/page";
import { Badge, Card, CardContent, ErrorState, Skeleton } from "@fsp/ui";

import { useLlmExamAdminDemoLlmExamGet } from "@/api/endpoints/admin/admin";
import { T } from "./text";

const L = T.llmExam;

const grantedText = (g: Record<string, number>) =>
  Object.entries(g).map(([k, n]) => `${k === "none" ? L.none : k}: ${n}`).join(" · ");

/** `/admin/demo/llm-exam`: LLM как кандидат — отчёт E27-1 и `ai_solvable` банка (E26-4). */
export default function LlmExam() {
  const q = useLlmExamAdminDemoLlmExamGet({ query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;
  return (
    <div data-testid="demo-llm-exam" className={PAGE.wide}>
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{L.title}</h1>
        <p className="text-14 text-muted">{L.lead}</p>
      </header>
      {q.isLoading && <Skeleton className="h-48" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />}
      {d && (
        <>
          <Card data-testid="demo-llm-report">
            <CardContent className="flex flex-col gap-3">
              {d.report ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="muted" data-testid="demo-simulation">{L.simulation}</Badge>
                    <span className="text-13 text-muted">{L.simulationText(d.report.seed, d.report.families)}</span>
                  </div>
                  {d.report.ai_solvable_share != null && <p className="text-14" data-testid="demo-ai-share">{L.share(d.report.ai_solvable_share)}</p>}
                  <table className="w-full text-left text-14">
                    <thead>
                      <tr className="text-13 text-muted"><th className="py-1 pr-3">{L.declared}</th><th className="py-1 pr-3">{L.granted}</th><th className="py-1">{L.needsConfirmation}</th></tr>
                    </thead>
                    <tbody>
                      {d.report.rows.map((r) => (
                        <tr key={r.declared} data-testid={`demo-llm-row-${r.declared}`} className="border-t border-hairline">
                          <td className="py-2 pr-3 font-semibold">{r.declared}</td>
                          <td className="py-2 pr-3">{grantedText(r.granted)}</td>
                          <td className="py-2"><Badge variant="muted">{L.flagged(r.flagged_share)}</Badge></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </>
              ) : (
                <p className="text-14 text-muted" data-testid="demo-no-report">{L.noReport}</p>
              )}
            </CardContent>
          </Card>
          <Card data-testid="demo-llm-bank">
            <CardContent className="flex flex-col gap-2">
              <h2 className="text-16 font-semibold">{L.bank}</h2>
              {d.bank.measured === 0 ? (
                <p className="text-14 text-muted">{L.bankEmpty}</p>
              ) : (
                <>
                  <p className="text-14">{L.bankText(d.bank.measured, d.bank.families, d.bank.solved_by_llm)}</p>
                  <h3 className="text-13 text-muted">{L.top}</h3>
                  <ul className="flex flex-col gap-1 text-14">
                    {d.bank.top.map((f) => (
                      <li key={f.slug} className="flex flex-wrap items-center gap-2">
                        <code>{f.slug}</code>
                        <Badge variant="muted">{f.ai_solvable.toFixed(2)}</Badge>
                        {f.ai_solvable >= 0.5 && <Badge>{L.needsConfirmation}</Badge>}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
