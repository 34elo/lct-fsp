import { useState } from "react";

import { cn } from "@/shared/lib/cn";
import { BlocklistTab, DistinctTab, HintsTab, ProvisionalTab } from "./SkillsLists";
import { MergesTab, QueueTab } from "./SkillsQueue";
import { SK } from "./text";

const TABS = ["queue", "merges", "distinct", "blocklist", "provisional", "hints"] as const;
type Tab = (typeof TABS)[number];

/** `/admin/skills` (G3): очередь слияний, «точно разные», стоп-лист, новые навыки, рост графа (E16-7). */
export default function AdminSkills() {
  const [tab, setTab] = useState<Tab>("queue");
  return (
    <div data-testid="admin-skills-page" className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{SK.title}</h1>
        <p className="text-14 text-muted">{SK.lead}</p>
      </header>
      <div role="tablist" aria-label={SK.title} className="flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            data-testid={`admin-sk-tab-${t}`}
            onClick={() => setTab(t)}
            className={cn("min-h-9 rounded-lg border px-3 text-14 font-semibold", tab === t ? "border-tint-200 bg-tint-100 text-brand-deep" : "border-hairline text-muted")}
          >
            {SK.tabs[t]}
          </button>
        ))}
      </div>
      {tab === "queue" && <QueueTab />}
      {tab === "merges" && <MergesTab />}
      {tab === "distinct" && <DistinctTab />}
      {tab === "blocklist" && <BlocklistTab />}
      {tab === "provisional" && <ProvisionalTab />}
      {tab === "hints" && <HintsTab />}
    </div>
  );
}
