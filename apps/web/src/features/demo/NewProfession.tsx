import { PAGE } from "@/shared/lib/page";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, Button, Card, CardContent, Skeleton } from "@fsp/ui";

import { useGetHintsAdminSkillsHintsGet, useListProfessionsAdminProfessionsGet } from "@/api/endpoints/admin/admin";
import { SAMPLE_CLUSTER, type ClusterView } from "./fixtures";
import { T } from "./text";
import { AdminPageHeader } from "@/features/admin/PageHeader";

const N = T.newProfession;

/** `/admin/demo/new-profession`: рост графа (E16-6/E16-7) → кластер → новая профессия (E13-1a). */
export default function NewProfession() {
  const hints = useGetHintsAdminSkillsHintsGet({ query: { retry: false } });
  const profs = useListProfessionsAdminProfessionsGet({ query: { retry: false } });
  const nav = useNavigate();
  const [i, setI] = useState(0);
  const found: ClusterView[] =
    hints.data?.status === 200
      ? hints.data.data.profession_candidates.map((c) => ({ skills: c.skills, support: c.support, covered: c.covered_by_professions }))
      : [];
  const real = found.length > 0;
  const clusters = real ? found : [SAMPLE_CLUSTER];
  const c = clusters[Math.min(i, clusters.length - 1)];
  const count = profs.data?.status === 200 ? profs.data.data.length : null;
  return (
    <div data-testid="demo-new-profession" className={PAGE.wide}>
      <AdminPageHeader title={N.title} tip={N.lead} />
      {hints.isLoading ? (
        <Skeleton className="h-40" />
      ) : (
        <>
          <p className="text-13 text-muted" data-testid="demo-cluster-source">{real ? N.real : N.sample}</p>
          <Card data-testid="demo-cluster">
            <CardContent className="flex flex-col gap-3">
              <h2 className="text-16 font-semibold">{N.step1}</h2>
              {clusters.length > 1 && (
                <div role="tablist" aria-label={N.pick} className="flex flex-wrap gap-1">
                  {clusters.map((x, k) => (
                    <button key={x.skills.join("|")} type="button" role="tab" aria-selected={k === i} onClick={() => setI(k)} className="min-h-9 rounded-lg border border-hairline px-3 text-13">
                      {x.skills.slice(0, 2).join(" + ")}
                    </button>
                  ))}
                </div>
              )}
              <h3 className="text-14 font-semibold">{N.step2}</h3>
              <span className="flex flex-wrap gap-1" data-testid="demo-cluster-skills">
                {c.skills.map((s) => <Badge key={s}>{s}</Badge>)}
              </span>
              <p className="text-13 text-muted">{N.members(c.support)} · {N.covered(Math.round(c.covered * 100))}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="flex flex-col gap-2">
              <h2 className="text-16 font-semibold">{N.step3}</h2>
              {count != null && (
                <p className="text-14" data-testid="demo-prof-count">{N.before(count)} · {N.after(count + 1)}</p>
              )}
              <p className="text-13 text-muted">{N.skills}</p>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => nav("/admin/professions")}>{N.create}</Button>
                <Button variant="outline" onClick={() => nav("/admin/skills")}>{N.growthLink}</Button>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
