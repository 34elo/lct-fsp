import { useState } from "react";
import { Link } from "react-router-dom";

import { Card, CardContent, ErrorState, Skeleton } from "@fsp/ui";

import { useGetDashboardAdminDashboardGet } from "@/api/endpoints/admin-dashboard/admin-dashboard";
import type { Counter, DayPoint } from "@/api/model";
import { PAGE } from "@/shared/lib/page";
import { AdminPageHeader } from "./PageHeader";
import { A, T, cell } from "./text";

const PERIODS = [7, 30, 90];

/** Столбики по дням: высота по максимуму ряда, скрытые дни — пустое место. Оси подписаны. */
function DayBars({ id, title, days }: { id: string; title: string; days: DayPoint[] }) {
  const values = days.map((d) => d.values[id] ?? null);
  const max = Math.max(1, ...values.map((v) => v ?? 0));
  return (
    <figure className="flex flex-col gap-1" data-testid={`analytics-chart-${id}`}>
      <figcaption className="sr-only">{A.chart(title)}</figcaption>
      <div className="flex h-16 items-end gap-px" role="img" aria-label={`${A.chart(title)}: максимум ${max}`}>
        {days.map((d, i) => (
          <div
            key={d.date}
            title={`${new Date(d.date).toLocaleDateString("ru-RU")}: ${values[i] ?? A.hiddenDay}`}
            className="min-w-px flex-1 rounded-sm bg-brand"
            style={{ height: values[i] === null ? 0 : `${Math.max(4, Math.round(((values[i] as number) / max) * 100))}%` }}
          />
        ))}
      </div>
      <div className="flex justify-between text-12 text-muted">
        <span>{new Date(days[0]!.date).toLocaleDateString("ru-RU")}</span>
        <span>{A.axisX}</span>
        <span>{new Date(days[days.length - 1]!.date).toLocaleDateString("ru-RU")}</span>
      </div>
    </figure>
  );
}

function CounterCard({ c, days }: { c: Counter; days: DayPoint[] }) {
  return (
    <Card data-testid={`analytics-${c.id}`}>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-14 font-semibold">{c.title}</p>
          <p className="font-mono text-24 font-semibold" data-testid="analytics-total">
            {cell(c.count, c.hidden)}
          </p>
        </div>
        {days.length > 0 && <DayBars id={c.id} title={c.title} days={days} />}
      </CardContent>
    </Card>
  );
}

/** `/federation/analytics` — «Аналитика» вместо «Качества» (E41-15): счётчики и динамика по дням. */
export default function Analytics() {
  const [days, setDays] = useState(30);
  const q = useGetDashboardAdminDashboardGet({ days }, { query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;

  return (
    <div className={PAGE.wide}>
      <AdminPageHeader title={A.title} tip={A.lead}>
        <div role="group" aria-label={T.dash.daysLabel} className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={days === p}
              onClick={() => setDays(p)}
              className={`min-h-9 rounded-lg border px-3 text-14 font-semibold ${days === p ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted"}`}
            >
              {T.dash.period(p)}
            </button>
          ))}
        </div>
      </AdminPageHeader>
      {q.isLoading && <Skeleton className="h-64" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
      {d && (
        <>
          <p className="text-13 text-muted">
            {A.byDay}: {A.axisY.toLowerCase()}. {T.dash.hiddenHint(d.min_cell)}
          </p>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {(d.counters ?? []).map((c) => (
              <CounterCard key={c.id} c={c} days={d.daily ?? []} />
            ))}
          </div>
          <Link to="/federation/funnel" className="self-start text-14 font-semibold text-brand-deep underline dark:text-brand-mid">
            {A.funnelLink}
          </Link>
        </>
      )}
    </div>
  );
}
