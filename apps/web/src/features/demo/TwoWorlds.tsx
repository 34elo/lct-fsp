import { PAGE } from "@/shared/lib/page";
import { useState } from "react";

import { Badge, Card, CardContent, ErrorState, NumberInput, Select, Skeleton } from "@fsp/ui";

import { useTwoWorldsAdminDemoTwoWorldsGet } from "@/api/endpoints/admin/admin";
import { T } from "./text";
import { AdminPageHeader } from "@/features/admin/PageHeader";

const TW = T.twoWorlds;

/** `/admin/demo/two-worlds`: одно семейство в двух мирах (`domain_for_vacancy`). */
export default function TwoWorlds() {
  const [family, setFamily] = useState("arch_blast_radius");
  const [seed, setSeed] = useState(7);
  const q = useTwoWorldsAdminDemoTwoWorldsGet({ family, seed }, { query: { retry: false } });
  const d = q.data?.status === 200 ? q.data.data : null;
  return (
    <div data-testid="demo-two-worlds" className={PAGE.wide}>
      <AdminPageHeader title={TW.title} tip={TW.lead} />
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1 text-13 text-muted">
          <span>{TW.family}</span>
          <Select
            data-testid="demo-family"
            aria-label={TW.family}
            value={family}
            onChange={(v) => v && setFamily(v)}
            options={(d?.choices ?? [family]).map((c) => ({ value: c, label: c }))}
            className="w-72 max-w-full text-ink"
          />
        </div>
        <div className="flex flex-col gap-1 text-13 text-muted">
          <span>{TW.seed}</span>
          <NumberInput data-testid="demo-seed" aria-label={TW.seed} min={0} value={seed} onChange={(v) => setSeed(Math.max(0, v ?? 0))} className="w-36" />
        </div>
      </div>
      {q.isLoading && <Skeleton className="h-48" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />}
      {d && (
        <>
          <p className="flex flex-wrap items-center gap-2 text-14" data-testid="demo-same-shape">
            <Badge variant={d.same_shape ? "default" : "muted"}>{d.same_shape ? TW.same : TW.differs}</Badge>
            <span className="text-muted">{TW.level(d.level)} · {TW.skill(d.skill)}</span>
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            {d.worlds.map((w, i) => (
              <Card key={w.domain} data-testid={`demo-world-${w.domain}`}>
                <CardContent className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-16 font-semibold">{TW.candidate(i + 1)}</h2>
                    <Badge>{w.domain_title}</Badge>
                    <span className="text-13 text-muted">{TW.company}: {w.company}</span>
                  </div>
                  <pre className="whitespace-pre-wrap break-words text-13 leading-relaxed" data-testid={`demo-stem-${w.domain}`}>{w.stem}</pre>
                  {w.options && (
                    <div className="flex flex-col gap-1">
                      <span className="text-13 text-muted">{TW.options}</span>
                      <ol className="list-decimal pl-5 text-14">
                        {w.options.map((o) => <li key={o}>{o}</li>)}
                      </ol>
                    </div>
                  )}
                  <p className="text-13 text-muted">{TW.time(w.time_limit_s)} · {TW.services}: {w.services.join(", ")}</p>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="text-12 text-muted">{TW.note}</p>
        </>
      )}
    </div>
  );
}
