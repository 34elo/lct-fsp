import { PAGE } from "@/shared/lib/page";
import { Badge, Card, CardContent, CardHeader, CardTitle, InfoTip, Skeleton } from "@fsp/ui";

import { useGetMetricsAdminMetricsGet } from "@/api/endpoints/admin-metrics/admin-metrics";
import type { AppAnalyticsMetricsStage as Stage } from "@/api/model";
import { BarChart } from "./Charts";
import { HEADLINES, type Headline } from "./headline";
import { QualityNav } from "./Nav";
import { byArea, report, STATUS_ORDER, type MetricRow, type Status } from "./report";
import { T } from "./text";
import { AdminPageHeader } from "@/features/admin/PageHeader";

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

const row = (id: string): MetricRow | undefined => report.rows.find((r) => r.id === id);

/** Причина «не измерено» без команд разработчика. */
const reason = (r: MetricRow | undefined) => (r?.note ?? "").replace(/\s*\(нужен[^)]*\)/, "").replace(/`/g, "");

function useOnline() {
  const q = useGetMetricsAdminMetricsGet({ days: 30 }, { query: { retry: false } });
  return { d: q.data?.status === 200 ? q.data.data : null, loading: q.isLoading };
}

function HeadlineCard({ h, online }: { h: Headline; online: { rate: number | null; loading: boolean } }) {
  const isOnline = h.id === "online";
  const r = isOnline ? undefined : row(h.id);
  const status: Status = isOnline ? (online.rate === null ? "unmeasured" : "info") : (r?.status ?? "unmeasured");
  const value = isOnline ? (online.loading ? "…" : pct(online.rate)) : (r?.value_text ?? "—");
  const target = isOnline ? "справочно" : (r?.target_text ?? "");
  const extra = (h.extra ?? []).flatMap((id) => row(id) ?? []);
  return (
    <Card data-testid={`headline-${h.id}`}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-16">
          <StatusDot status={status} />
          <span className="min-w-0 flex-1">{h.title}</span>
          <InfoTip title={h.title} label={`Как считается: ${h.title}`} side="bottom" data-testid="headline-tip">
            <span className="flex flex-col gap-2">
              <span>
                <b>{T.method}.</b> {h.method}
              </span>
              {extra.length > 0 && (
                <span className="flex flex-col gap-0.5">
                  {extra.map((e) => (
                    <span key={e.id}>
                      {e.name}: <b className="font-mono">{e.value_text}</b>
                    </span>
                  ))}
                </span>
              )}
            </span>
          </InfoTip>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <p className="flex flex-wrap items-baseline gap-3">
          <span className="font-mono text-28 font-semibold" data-testid={`headline-value-${h.id}`}>
            {value}
          </span>
          {target && (
            <span className="text-13 text-muted">
              {T.target}: <span className="font-mono">{target}</span>
            </span>
          )}
        </p>
        <p className="text-13 font-medium">{T.status[status]}</p>
        {status === "unmeasured" && <p className="text-13 text-muted">{(!isOnline && reason(r)) || T.notMeasuredHint}</p>}
        <p className="text-14 text-muted">{h.means}</p>
      </CardContent>
    </Card>
  );
}

const GRADES = ["junior", "middle", "senior"] as const;
const GRADE_RU: Record<string, string> = { junior: "Junior", middle: "Middle", senior: "Senior" };
const num = (id: string) => row(id)?.value ?? null;
const percent = (v: number) => `${Math.round(v * 100)} %`;

function Charts() {
  const granted = GRADES.map((g) => num(`llm_${g}_granted`));
  const flagged = GRADES.map((g) => num(`llm_${g}_flagged`));
  const showLlm = [...granted, ...flagged].some((v) => v !== null);
  const calib = [num("calib30"), num("calib100")];
  const showCalib = calib.some((v) => v !== null);
  if (!showLlm && !showCalib) return null;
  return (
    <section className="flex flex-col gap-3" aria-labelledby="charts-h">
      <h2 id="charts-h" className="text-20 font-semibold">
        {T.charts}
      </h2>
      <div className="grid gap-6 lg:grid-cols-2">
        {showLlm && (
          <Card>
            <CardContent className="pt-4">
              <BarChart
                title="ИИ-кандидат выдаёт себя за более сильного: что получает и ловится ли"
                xLabel="Грейд, который заявил ИИ-кандидат"
                yLabel="Доля прогонов, %"
                categories={GRADES.map((g) => GRADE_RU[g])}
                series={[
                  { name: "Получил заявленный грейд", color: "var(--signal)", values: granted },
                  { name: "Сработал индекс честности", color: "var(--brand-mid)", values: flagged },
                ]}
                max={1}
                format={percent}
              />
              <p className="mt-2 text-13 text-muted">Чем выше заявленный грейд, тем реже ИИ-кандидат его получает и тем чаще его ловит индекс честности.</p>
            </CardContent>
          </Card>
        )}
        {showCalib && (
          <Card>
            <CardContent className="pt-4">
              <BarChart
                title="Точность оценки растёт с числом ответов"
                xLabel="Сколько ответов дал кандидат"
                yLabel="Ошибка оценки (RMSE), меньше — лучше"
                categories={["30 ответов", "100 ответов"]}
                series={[{ name: "Ошибка оценки", color: "var(--brand-mid)", values: calib }]}
                max={0.6}
                target={{ value: 0.4, label: "цель на 30 ответах: 0,4" }}
                format={(v) => v.toFixed(2).replace(".", ",")}
              />
              <p className="mt-2 text-13 text-muted">Мало ответов — оценка грубая; к сотне она уточняется.</p>
            </CardContent>
          </Card>
        )}
      </div>
    </section>
  );
}

function Online({ d, loading }: { d: ReturnType<typeof useOnline>["d"]; loading: boolean }) {
  return (
    <section className="flex flex-col gap-3" aria-labelledby="online-h">
      <div>
        <h2 id="online-h" className="text-20 font-semibold">
          {T.online}
        </h2>
        <p className="text-14 text-muted">{T.onlineLead}</p>
      </div>
      {loading && <Skeleton className="h-32" />}
      {!loading && !d && <p className="text-14 text-muted">{T.onlineEmpty}</p>}
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

/** `/admin/quality` — главные метрики со светофором и методикой (E39-32); подробности — свёрнуты, живые прогоны — отдельной вкладкой. */
export default function Quality() {
  const { d, loading } = useOnline();
  const unavailable = Object.entries(report.components).filter(([, c]) => !c.ok);
  return (
    <div className={PAGE.wide}>
      <AdminPageHeader title={T.title} tip={T.lead} />
      <QualityNav />
      <section className="flex flex-col gap-3" aria-labelledby="head-h">
        <div>
          <h2 id="head-h" className="text-20 font-semibold">
            {T.headline}
          </h2>
          <p className="text-14 text-muted">{T.headlineLead}</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {HEADLINES.map((h) => (
            <HeadlineCard key={h.id} h={h} online={{ rate: d?.invites.accept_rate ?? null, loading }} />
          ))}
        </div>
      </section>
      <Charts />
      <Online d={d} loading={loading} />
      <details className="rounded-lg border border-hairline p-4" data-testid="all-metrics">
        <summary className="cursor-pointer text-16 font-semibold">{T.details}</summary>
        <div className="mt-3 flex flex-col gap-4">
          <p className="text-14 text-muted">{T.detailsLead}</p>
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
                          {r.note && <span className="block text-12 text-muted">{r.status === "unmeasured" ? reason(r) : r.note}</span>}
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
        </div>
      </details>
    </div>
  );
}
