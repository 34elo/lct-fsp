import { PAGE } from "@/shared/lib/page";
import { Card, CardContent, CardHeader, CardTitle } from "@fsp/ui";

import { QualityNav } from "./Nav";
import { StatusDot } from "./Quality";
import { report } from "./report";
import { T } from "./text";

const RELATED = ["integrity_fpr", "fsp_effort", "unconfirmed_below", "grade_acc_all"];

/** `/admin/quality/fairness` (Q2) — справедливость подбора: влияние ФСП на ранжирование. */
export default function Fairness() {
  const main = report.rows.find((r) => r.id === "fairness");
  const related = RELATED.flatMap((id) => report.rows.filter((r) => r.id === id));
  return (
    <div className={PAGE.wide}>
      <header>
        <h1 className="text-24 font-semibold">{T.fair.title}</h1>
        <p className="max-w-2xl text-14 text-muted">{T.fair.lead}</p>
      </header>
      <QualityNav />
      <Card>
        <CardHeader>
          <CardTitle>{T.fair.ratio}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          {main ? (
            <>
              <p className="flex flex-wrap items-center gap-3">
                <StatusDot status={main.status} />
                <span className="font-mono text-24 font-semibold" data-testid="fair-value">
                  {main.value_text}
                </span>
                <span className="font-mono text-14 text-muted">{main.target_text}</span>
              </p>
              <p className="text-14 text-muted">{T.fair.ratioHint}</p>
              <p className="text-14" data-testid="fair-verdict">
                {main.status === "red" || main.status === "yellow" ? T.fair.action : main.status === "green" ? T.fair.ok : T.fair.none}
              </p>
            </>
          ) : (
            <p className="text-14 text-muted">{T.fair.none}</p>
          )}
        </CardContent>
      </Card>
      {related.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{T.fair.related}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {related.map((r) => (
              <p key={r.id} className="flex flex-wrap items-center gap-3 text-14">
                <StatusDot status={r.status} />
                <span className="min-w-0 flex-1">{r.name}</span>
                <span className="font-mono font-semibold">{r.value_text}</span>
                <span className="font-mono text-muted">{r.target_text}</span>
              </p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
