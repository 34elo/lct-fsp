import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle, ErrorState, Skeleton, cardInteractive, cn } from "@fsp/ui";

import { useGetSummaryAdminSummaryGet } from "@/api/endpoints/admin-dashboard/admin-dashboard";
import type { QueueCount } from "@/api/model";
import { PAGE } from "@/shared/lib/page";
import { AdminPageHeader } from "./PageHeader";
import { H, type QueueId } from "./text";

function QueueTile({ q }: { q: QueueCount }) {
  const meta = H.queues[q.id as QueueId];
  if (!meta) return null;
  const waiting = (q.count ?? 0) > 0;
  return (
    <li>
      <Link
        to={meta.to}
        data-testid={`queue-${q.id}`}
        aria-label={`${meta.title}: ${q.count ?? H.unknown}. ${H.open}`}
        className={cn(
          "flex h-full flex-col gap-1 rounded-xl border p-3 sm:min-h-24 sm:p-4",
          cardInteractive,
          waiting ? "border-tint-200 bg-tint-100" : "border-hairline bg-card",
        )}
      >
        <span className="flex items-baseline justify-between gap-3">
          <span className="text-14 font-semibold">{meta.title}</span>
          <span className={cn("font-mono text-24 font-semibold", waiting ? "text-brand-deep dark:text-brand-mid" : "text-muted")} data-testid="queue-count">
            {q.count ?? "—"}
          </span>
        </span>
        <span className="text-13 text-muted">{q.count === null ? H.unknown : meta.hint}</span>
      </Link>
    </li>
  );
}

/** `/federation` — главная админки: «Что требует вас» и что работает само. */
export default function Home() {
  const q = useGetSummaryAdminSummaryGet({ query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;
  const clear = d !== null && d.total === 0 && d.queues.every((x) => x.count !== null);

  return (
    <div className={PAGE.wide}>
      <AdminPageHeader title={H.title} tip={H.lead} />

      <Card data-testid="admin-needs">
        <CardHeader>
          <CardTitle>{H.needs}</CardTitle>
          <p className="text-14 text-muted">{H.needsLead}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {q.isLoading && (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-hidden>
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
          )}
          {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
          {clear && (
            <p className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success-fg" data-testid="admin-clear">
              {H.allClear} {H.allClearHint}
            </p>
          )}
          {d && (
            <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {d.queues.map((x) => (
                <QueueTile key={x.id} q={x} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card data-testid="admin-auto">
        <CardHeader>
          <CardTitle>{H.auto}</CardTitle>
          <p className="text-14 text-muted">{H.autoLead}</p>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {H.autoItems.map((a) => (
              <li key={a.title} className="flex flex-col gap-1 rounded-lg border border-hairline p-3">
                <span className="text-14 font-semibold">{a.title}</span>
                <span className="text-13 text-muted">{a.text}</span>
              </li>
            ))}
          </ul>
          <p className="text-13 text-muted">
            {H.analytics.lead}{" "}
            <Link to="/federation/funnel" className="font-semibold text-brand-deep underline dark:text-brand-mid">
              {H.analytics.funnel}
            </Link>{" "}
            {H.analytics.and}{" "}
            <Link to="/federation/analytics" className="font-semibold text-brand-deep underline dark:text-brand-mid">
              {H.analytics.quality}
            </Link>
            .
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
