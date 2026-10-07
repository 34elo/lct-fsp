import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Card, CardContent, CardHeader, CardTitle, ErrorState, Skeleton } from "@fsp/ui";

import { useGetDashboardAdminDashboardGet } from "@/api/endpoints/admin-dashboard/admin-dashboard";
import type { AppAnalyticsDashboardStage as Stage, Ratio } from "@/api/model";
import { Summary } from "@/features/quality/Quality";
import { T as QT } from "@/features/quality/text";
import { cell, T } from "./text";

const PERIODS = [7, 30, 90];

function StageRow({ s, max }: { s: Stage; max: number }) {
  const width = s.hidden || s.count === null || max === 0 ? 0 : Math.max(2, Math.round((s.count / max) * 100));
  return (
    <li className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-14 font-semibold">{s.title}</span>
        <span className="font-mono text-18 font-semibold" data-testid={`stage-${s.id}`}>
          {cell(s.count, s.hidden)}
        </span>
      </div>
      <div className="h-2 rounded-full bg-tint-100" aria-hidden>
        <div className="h-2 rounded-full bg-brand" style={{ width: `${width}%` }} />
      </div>
      {!s.hidden && (
        <p className="flex flex-wrap gap-x-3 text-12 text-muted">
          {s.pct_of_registered !== null && <span>{T.dash.ofRegistered(s.pct_of_registered)}</span>}
          {s.pct_of_previous !== null && <span>{T.dash.ofPrevious(s.pct_of_previous)}</span>}
        </p>
      )}
    </li>
  );
}

function RatioCard({ title, r, min }: { title: string; r: Ratio; min: number }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1">
        <p className="text-13 text-muted">{title}</p>
        <p className="font-mono text-24 font-semibold" data-testid="ratio-value">
          {r.hidden || r.count === null ? T.hidden : T.dash.ratio(r.count, r.of, r.pct)}
        </p>
        {r.hidden && <p className="text-12 text-muted">{T.dash.hiddenHint(min)}</p>}
      </CardContent>
    </Card>
  );
}

/** `/federation` — дашборд ФСП (F1): воронка и доли. Ячейки меньше порога приходят скрытыми. */
export default function Dashboard() {
  const [days, setDays] = useState(30);
  const q = useGetDashboardAdminDashboardGet({ days }, { query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;
  const max = d ? Math.max(0, ...d.funnel.map((s) => (s.hidden ? 0 : (s.count ?? 0)))) : 0;

  return (
    <div className="flex flex-col gap-5 p-4 md:p-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-24 font-semibold">{T.dash.title}</h1>
          <p className="max-w-2xl text-14 text-muted">{T.dash.lead}</p>
        </div>
        <div role="group" aria-label={T.dash.daysLabel} className="flex gap-1">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              aria-pressed={days === p}
              onClick={() => setDays(p)}
              className={`min-h-9 rounded-lg border px-3 text-14 font-semibold ${days === p ? "border-tint-200 bg-tint-100 text-brand-deep" : "border-hairline text-muted"}`}
            >
              {T.dash.period(p)}
            </button>
          ))}
        </div>
      </header>

      {q.isLoading && <Skeleton className="h-64" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
      {d && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{T.dash.funnel}</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="flex flex-col gap-4">
                {d.funnel.map((s) => (
                  <StageRow key={s.id} s={s} max={max} />
                ))}
              </ol>
            </CardContent>
          </Card>
          <div className="grid gap-4 sm:grid-cols-2">
            <RatioCard title={T.dash.fspShare} r={d.fsp_share} min={d.min_cell} />
            <RatioCard title={T.dash.navigator} r={d.navigator_to_competition} min={d.min_cell} />
          </div>
          <Badge variant="muted" className="self-start">
            {T.dash.period(d.days)}
          </Badge>
          <Card>
            <CardHeader>
              <CardTitle>{QT.fspBlock}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <p className="text-14 text-muted">{QT.fspBlockLead}</p>
              <Summary />
              <Link to="/admin/quality" className="self-start text-14 font-semibold text-brand-deep underline">
                {QT.open}
              </Link>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
