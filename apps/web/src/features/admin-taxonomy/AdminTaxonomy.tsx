import { PAGE } from "@/shared/lib/page";
import { useState } from "react";

import { CardsTab } from "./Cards";
import { ProfessionsTab } from "./Professions";
import { cn } from "@fsp/ui";
import { T } from "./text";
import { AdminPageHeader } from "@/features/admin/PageHeader";

type Tab = "professions" | "cards";

/** Админ: профессии теста и карточки навыков (E13-4a). */
export default function AdminTaxonomy() {
  const [tab, setTab] = useState<Tab>("professions");
  return (
    <div data-testid="admin-taxonomy-page" className={PAGE.wide}>
      <AdminPageHeader title={T.title} tip={T.lead} />
      <div role="tablist" aria-label={T.title} className="flex flex-wrap gap-1">
        {(["professions", "cards"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            data-testid={`admin-taxonomy-tab-${t}`}
            onClick={() => setTab(t)}
            className={cn("min-h-9 rounded-lg border px-3 text-14 font-semibold", tab === t ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted")}
          >
            {T.tabs[t]}
          </button>
        ))}
      </div>
      {tab === "professions" ? <ProfessionsTab /> : <CardsTab />}
    </div>
  );
}
