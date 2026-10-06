import { EmptyState, ErrorState, Skeleton } from "@fsp/ui";
import { Link, useSearchParams } from "react-router-dom";

import { useMyGraphCandidatesMeGraphGet } from "@/api/endpoints/graph/graph";
import { MyGraphCandidatesMeGraphGetDepth, MyGraphCandidatesMeGraphGetSkills } from "@/api/model";
import EvidenceGraph from "@/features/graph/EvidenceGraph";
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

/** Граф доказательств кандидата (`/me/graph`, G1/G2). */
export default function Graph() {
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
      <div role="status" aria-label={T.loading} data-testid="graph-loading" className="flex flex-col gap-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
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
    body = <EvidenceGraph graph={q.data.data} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="font-mono text-xl font-semibold">{T.title}</h1>
        <p className="text-sm text-muted">{T.lead}</p>
      </header>
      <div data-testid="graph-filters" role="group" aria-label={T.filtersLabel} className="flex flex-col gap-2 md:flex-row md:gap-6">
        <Toggle label={T.skillsLabel} value={skills} testid="graph-skills" onChange={(v) => set("skills", v)} options={[["top", T.skillsTop], ["all", T.skillsAll]]} />
        <Toggle label={T.depthLabel} value={depth} testid="graph-depth" onChange={(v) => set("depth", v)} options={[["facts", T.depthFacts], ["competitions", T.depthCompetitions]]} />
      </div>
      <section aria-label={T.title} className="rounded-xl border border-hairline bg-card p-4 md:p-5">
        {body}
      </section>
    </div>
  );
}
