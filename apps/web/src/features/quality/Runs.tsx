import { PAGE } from "@/shared/lib/page";
import { useState } from "react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Skeleton } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";

import { useCreateRunAdminLiveRunsPost, useListRunsAdminLiveRunsGet } from "@/api/endpoints/live-runs/live-runs";
import type { RunOut } from "@/api/model";
import { QualityNav } from "./Nav";
import { T } from "./text";

type Scenario = "candidate" | "employer";
const R = T.runs;
const num = (v: number | null | undefined, unit = "") => (v === null || v === undefined ? "—" : `${Math.round(v * 10) / 10}${unit}`);
const dur = (s: number | null) => (s === null ? "—" : s >= 60 ? `${Math.round(s / 60)} мин` : `${Math.round(s)} с`);

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-hairline px-3 py-2">
      <p className="text-12 text-muted">{label}</p>
      <p className="font-mono text-20 font-semibold">{value}</p>
    </div>
  );
}

function CreateRun({ scenario }: { scenario: Scenario }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [created, setCreated] = useState<RunOut | null>(null);
  const [copied, setCopied] = useState(false);
  const m = useCreateRunAdminLiveRunsPost();
  const link = created ? `${window.location.origin}${created.path}` : "";

  async function submit() {
    setCreated(null);
    setCopied(false);
    const res = await m.mutateAsync({ data: { scenario, notes: notes.trim() || null } }).catch(() => null);
    if (res && res.status === 201) {
      setCreated(res.data);
      setNotes("");
      void qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).includes("/admin/live-runs") });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{R.create}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input aria-label={R.notes} placeholder={R.notes} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={300} />
          <Button onClick={submit} disabled={m.isPending}>
            {m.isPending ? R.creating : `${R.create}: ${R.scenario[scenario].toLowerCase()}`}
          </Button>
        </div>
        {m.isError && (
          <p role="alert" className="text-14 text-error">
            {R.createError}
          </p>
        )}
        {created && (
          <div className="flex flex-col gap-1 text-14" data-testid="run-link">
            <span className="text-muted">{R.link}</span>
            <div className="flex flex-wrap items-center gap-2">
              <code className="break-all font-mono">{link}</code>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  void navigator.clipboard?.writeText(link);
                  setCopied(true);
                }}
              >
                {copied ? R.copied : R.copy}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** `/admin/quality/runs` (Q3) — живые прогоны: сводка, список, создание приглашения. */
export default function Runs() {
  const [scenario, setScenario] = useState<Scenario>("candidate");
  const q = useListRunsAdminLiveRunsGet({ scenario }, { query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;
  const forbidden = q.data?.status === 403;
  return (
    <div className={PAGE.wide}>
      <header>
        <h1 className="text-24 font-semibold">{R.title}</h1>
        <p className="max-w-2xl text-14 text-muted">{R.lead}</p>
      </header>
      <QualityNav />
      <div className="flex gap-2" role="group" aria-label={R.cols.scenario}>
        {(["candidate", "employer"] as const).map((s) => (
          <Button key={s} variant={scenario === s ? "default" : "outline"} size="sm" aria-pressed={scenario === s} onClick={() => setScenario(s)}>
            {R.scenario[s]}
          </Button>
        ))}
      </div>
      <CreateRun scenario={scenario} />
      {q.isLoading && <Skeleton className="h-32" />}
      {forbidden && <p className="text-14 text-muted">{R.forbidden}</p>}
      {!q.isLoading && !d && !forbidden && <p className="text-14 text-muted">{R.error}</p>}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5" data-testid="run-summary">
            <Stat label={R.summary.runs} value={`${d.summary.finished} / ${d.summary.runs}`} />
            <Stat label={R.summary.success} value={num(d.summary.task_success_pct, " %")} />
            <Stat label={R.summary.time} value={dur(d.summary.median_time_s)} />
            <Stat label={R.summary.sus} value={num(d.summary.median_sus)} />
            <Stat label={R.summary.agree} value={num(d.summary.category_agree_pct, " %")} />
          </div>
          {d.items.length === 0 ? (
            <p className="text-14 text-muted">{R.empty}</p>
          ) : (
            <Card>
              <CardContent className="overflow-x-auto pt-4">
                <table className="w-full text-left text-14">
                  <thead className="text-12 text-muted">
                    <tr>
                      {Object.values(R.cols).map((c) => (
                        <th key={c} className="py-1 pr-3 font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((r) => (
                      <tr key={r.id} className="border-t border-hairline align-top">
                        <td className="py-2 pr-3">{R.scenario[r.scenario]}</td>
                        <td className="py-2 pr-3">
                          <Badge variant="muted">{R.status[r.status]}</Badge>
                        </td>
                        <td className="py-2 pr-3 font-mono">{`${r.tasks_done}/${r.tasks_total}`}</td>
                        <td className="py-2 pr-3 font-mono">{dur(r.total_time_s)}</td>
                        <td className="py-2 pr-3 font-mono">{num(r.sus_score)}</td>
                        <td className="py-2 pr-3">{r.stuck_task ?? "—"}</td>
                        <td className="py-2">{r.category_agree === null ? "—" : r.category_agree ? R.yes : R.no}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
