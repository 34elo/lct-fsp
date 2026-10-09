import { EmptyState, ErrorState, EvidenceGraph, H2, Panel, SkeletonChart } from "@fsp/ui";
import { Gloss } from "@/shared/Gloss";
import { Link, useSearchParams } from "react-router-dom";

import { useMyGraphCandidatesMeGraphGet } from "@/api/endpoints/graph/graph";
import { MyGraphCandidatesMeGraphGetDepth, MyGraphCandidatesMeGraphGetSkills } from "@/api/model";
import { GraphList } from "@/features/graph/GraphList";
import { slugOf } from "@/features/graph/layout";
import { T } from "@/features/graph/text";

function Toggle<V extends string>({ label, value, options, onChange, testid }: { label: string; value: V; options: [V, string][]; onChange: (v: V) => void; testid: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
      <span className="text-[13px] text-muted">{label}</span>
      {options.map(([v, text]) => (
        <button
          key={v}
          type="button"
          data-testid={`${testid}-${v}`}
          aria-pressed={value === v}
          onClick={() => onChange(v)}
          className={`min-h-11 rounded-lg border px-3 text-sm font-semibold ${value === v ? "border-brand-fg bg-brand text-on-brand" : "border-hairline bg-card text-ink"}`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

/** Граф доказательств: вкладка «Граф» профиля (`/me/profile?tab=graph`, E38-6). Фильтры живут в адресе. */
export default function GraphView() {
  const [sp, setSp] = useSearchParams();
  const skills = sp.get("skills") === "all" ? MyGraphCandidatesMeGraphGetSkills.all : MyGraphCandidatesMeGraphGetSkills.top;
  const depth = sp.get("depth") === "competitions" ? MyGraphCandidatesMeGraphGetDepth.competitions : MyGraphCandidatesMeGraphGetDepth.facts;
  const q = useMyGraphCandidatesMeGraphGet({ skills, depth }, { query: { retry: false } });
  const set = (k: string, v: string) =>
    setSp((prev) => {
      const n = new URLSearchParams(prev);
      n.set(k, v);
      return n;
    }, { replace: true });

  let body: React.ReactNode;
  if (q.isPending) {
    body = (
      <div data-testid="graph-loading">
        <SkeletonChart height={420} />
      </div>
    );
  } else if (q.isError || q.data.status !== 200) {
    body = <ErrorState title={T.errorTitle} description={T.errorDescription} onRetry={() => void q.refetch()} />;
  } else if (q.data.data.nodes.filter((n) => n.type !== "candidate").length === 0) {
    body = (
      <div data-testid="graph-empty">
        <EmptyState title={T.emptyTitle} description={T.emptyDescription} action={<Link to="/me/profile/edit" className="inline-flex min-h-11 items-center font-semibold text-brand-fg">{T.emptyAction}</Link>} />
      </div>
    );
  } else {
    const graph = q.data.data;
    body = (
      <div data-testid="graph-root" className="flex flex-col gap-4">
        <EvidenceGraph
          data={graph}
          title={null}
          info={null}
          renderSkillAction={(n) => (
            <Link to={`/me/skills/${slugOf(n.id)}`} className="inline-flex min-h-11 items-center text-13 font-semibold text-brand-fg" aria-label={`${n.label}: ${T.skillLink}`}>
              {T.skillLink}
            </Link>
          )}
        />
        <details data-testid="graph-list-toggle" className="group">
          <summary className="inline-flex min-h-11 cursor-pointer items-center text-14 font-semibold text-brand-fg">{T.listToggle}</summary>
          <GraphList graph={graph} />
        </details>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4" data-testid="graph-view">
      <p className="text-14 text-muted">{T.lead}</p>
      <div data-testid="graph-filters" role="group" aria-label={T.filtersLabel} className="flex flex-col gap-2 md:flex-row md:gap-6">
        <Toggle label={T.skillsLabel} value={skills} testid="graph-skills" onChange={(v) => set("skills", v)} options={[["top", T.skillsTop], ["all", T.skillsAll]]} />
        <Toggle label={T.depthLabel} value={depth} testid="graph-depth" onChange={(v) => set("depth", v)} options={[["facts", T.depthFacts], ["competitions", T.depthCompetitions]]} />
      </div>
      <Panel aria-label={T.title} className="p-4 md:p-5">
        <Gloss k="graph" className="mb-3">
          <H2>{T.title}</H2>
        </Gloss>
        {body}
      </Panel>
    </div>
  );
}
