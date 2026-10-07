import { Badge, Card, CardContent, CardHeader, CardTitle, Skeleton } from "@fsp/ui";

import { useGetMetricsAdminMetricsGet } from "@/api/endpoints/admin-metrics/admin-metrics";
import type { AppAnalyticsMetricsStage as Stage } from "@/api/model";
import { byArea, report, STATUS_ORDER, type Status } from "./report";
import { T } from "./text";

const DOT: Record<Status, string> = {
  green: "bg-success",
  yellow: "bg-warning",
  red: "bg-error",
  unmeasured: "bg-muted",
  info: "bg-hairline",
};

export function StatusDot({ status }: { status: Status }) {
  return <span role="img" aria-label={T.status[status]} title={T.status[status]} className={`inline-block h-3 w-3 shrink-0 rounded-full ${DOT[status]}`} />;
}

/** Счётчики светофора: выполнено / почти / не выполнено / не измерено / справочно. */
export function Summary() {
  return (
    <ul className="flex flex-wrap gap-2" data-testid="traffic-summary">
      {STATUS_ORDER.map((s) => (
        <li key={s} className="flex items-center gap-2 rounded-lg border border-hairline px-3 py-1.5 text-14">
          <StatusDot status={s} />
          <span className="font-mono font-semibold" data-testid={`sum-${s}`}>
            {report.summary[s] ?? 0}
          </span>
          <span className="text-muted">{T.counts[s]}</span>
        </li>
      ))}
    </ul>
  );
}

function StageList({ stages }: { stages: Stage[] }) {
  const shown = stages.filter((s) => s.available);
  if (shown.length === 0) return <p className="text-14 text-muted">{T.onlineEmpty}</p>;
  return (
    <ol className="flex flex-col gap-1.5">
      {shown.map((s) => (
        <li key={s.id} className="flex items-baseline justify-between gap-3 text-14">
          <span>{s.title}</span>
          <span className="font-mono font-semibold">{s.hidden || s.count === null ? T.hidden : s.count}</span>
        </li>
      ))}
    </ol>
  );
}

const pct = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)} %`);

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <p className="flex justify-between gap-3">
      <span>{label}</span>
      <span className="font-mono font-semibold">{value}</span>
    </p>
  );
}

function Online() {
  const q = useGetMetricsAdminMetricsGet({ days: 30 }, { query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;
  return (
    <section className="flex flex-col gap-3" aria-labelledby="online-h">
      <div>
        <h2 id="online-h" className="text-20 font-semibold">
          {T.online}
        </h2>
        <p className="text-14 text-muted">{T.onlineLead}</p>
      </div>
      {q.isLoading && <Skeleton className="h-32" />}
      {!q.isLoading && !d && <p className="text-14 text-muted">{T.onlineEmpty}</p>}
      {d && (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>{T.candidateFunnel}</CardTitle>
            </CardHeader>
            <CardContent>
              <StageList stages={d.candidate_funnel.stages} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{T.employerFunnel}</CardTitle>
            </CardHeader>
            <CardContent>
              <StageList stages={d.employer_funnel.stages} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{T.invites}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1.5 text-14">
              <Row label={T.sent} value={d.invites.sent ?? T.hidden} />
              <Row label={T.accepted} value={d.invites.accepted ?? T.hidden} />
              <Row label={T.acceptRate} value={pct(d.invites.accept_rate)} />
              <Row label={T.respond72} value={pct(d.invites.respond_72h_rate)} />
              <Badge variant="muted" className="mt-1 self-start">
                {T.period(d.days)}
              </Badge>
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  );
}

/** `/admin/quality` (Q1) — минимальная страница качества: светофор офлайн-метрик и онлайн-воронки. */
export default function Quality() {
  const unavailable = Object.entries(report.components).filter(([, c]) => !c.ok);
  return (
    <div className="flex flex-col gap-6 p-4 md:p-6">
      <header>
        <h1 className="text-24 font-semibold">{T.title}</h1>
        <p className="max-w-2xl text-14 text-muted">{T.lead}</p>
      </header>
      <Summary />
      {unavailable.length > 0 && (
        <ul className="flex flex-col gap-1 text-13 text-muted">
          {unavailable.map(([k, c]) => (
            <li key={k}>{T.unavailable(k, c.reason)}</li>
          ))}
        </ul>
      )}
      {byArea(report.rows).map(([area, rows]) => (
        <Card key={area}>
          <CardHeader>
            <CardTitle>{area}</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-left text-14">
              <thead className="text-12 text-muted">
                <tr>
                  <th className="w-6 py-1" />
                  <th className="py-1 pr-3 font-medium">{T.metric}</th>
                  <th className="py-1 pr-3 font-medium">{T.value}</th>
                  <th className="py-1 font-medium">{T.target}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-hairline align-top">
                    <td className="py-2">
                      <StatusDot status={r.status} />
                    </td>
                    <td className="py-2 pr-3">
                      {r.name}
                      {r.note && <span className="block text-12 text-muted">{r.note}</span>}
                    </td>
                    <td className="py-2 pr-3 font-mono font-semibold" data-testid={`val-${r.id}`}>
                      {r.value_text}
                    </td>
                    <td className="py-2 font-mono text-muted">{r.target_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      ))}
      <Online />
    </div>
  );
}
