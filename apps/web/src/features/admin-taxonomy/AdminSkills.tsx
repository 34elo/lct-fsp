import { PAGE } from "@/shared/lib/page";
import { useState } from "react";

import { BlocklistTab, DistinctTab, HintsTab, ProvisionalTab } from "./SkillsLists";
import { GraphTab } from "./SkillsGraph";
import { MergesTab, QueueTab } from "./SkillsQueue";
import { cn } from "@fsp/ui";
import { SK } from "./text";
import { AdminPageHeader } from "@/features/admin/PageHeader";

const TABS = ["graph", "queue", "merges", "distinct", "blocklist", "provisional", "hints"] as const;
type Tab = (typeof TABS)[number];

/** `/admin/skills` (G3): очередь слияний, «точно разные», стоп-лист, новые навыки, рост графа (E16-7). */
export default function AdminSkills() {
  const [tab, setTab] = useState<Tab>("graph");
  return (
    <div data-testid="admin-skills-page" className={PAGE.wide}>
      <AdminPageHeader title={SK.title} tip={SK.lead} />
      <div role="tablist" aria-label={SK.title} className="flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            data-testid={`admin-sk-tab-${t}`}
            onClick={() => setTab(t)}
            className={cn("min-h-9 rounded-lg border px-3 text-14 font-semibold", tab === t ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted")}
          >
            {SK.tabs[t]}
          </button>
        ))}
      </div>
      {tab === "graph" && <GraphTab onOpen={setTab} />}
      {tab === "queue" && <QueueTab />}
      {tab === "merges" && <MergesTab />}
      {tab === "distinct" && <DistinctTab />}
      {tab === "blocklist" && <BlocklistTab />}
      {tab === "provisional" && <ProvisionalTab />}
      {tab === "hints" && <HintsTab />}
    </div>
  );
}
