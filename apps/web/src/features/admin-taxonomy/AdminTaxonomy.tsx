import { useState } from "react";

import { CardsTab } from "./Cards";
import { ProfessionsTab } from "./Professions";
import { cn } from "@fsp/ui";
import { T } from "./text";

type Tab = "professions" | "cards";

/** Админ: профессии теста и карточки навыков (E13-4a). */
export default function AdminTaxonomy() {
  const [tab, setTab] = useState<Tab>("professions");
  return (
    <div data-testid="admin-taxonomy-page" className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{T.title}</h1>
        <p className="text-14 text-muted">{T.lead}</p>
      </header>
      <div role="tablist" aria-label={T.title} className="flex flex-wrap gap-1">
        {(["professions", "cards"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            data-testid={`admin-taxonomy-tab-${t}`}
            onClick={() => setTab(t)}
            className={cn("min-h-9 rounded-lg border px-3 text-14 font-semibold", tab === t ? "border-tint-200 bg-tint-100 text-brand-deep" : "border-hairline text-muted")}
          >
            {T.tabs[t]}
          </button>
        ))}
      </div>
      {tab === "professions" ? <ProfessionsTab /> : <CardsTab />}
    </div>
  );
}
