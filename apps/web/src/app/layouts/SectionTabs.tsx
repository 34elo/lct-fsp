import { NavLink, useLocation } from "react-router-dom";

import { cn } from "@fsp/ui";

import type { NavItem } from "@/app/routes";
import { activeNav } from "./shell-meta";

/** Вкладки открытого раздела меню (E35-1) — внутри страницы, над её содержимым (E39-4), а не второй строкой шапки. */
export function SectionTabs({ nav, counts }: { nav: NavItem[]; counts?: Record<string, number | undefined> }) {
  const tabs = activeNav(nav, useLocation().pathname)?.tabs;
  if (!tabs?.length) return null;
  return (
    <div className="mx-auto w-full max-w-[1328px] px-4 pt-4 md:px-6">
      <div className="border-b border-hairline">
        <nav aria-label="Вкладки раздела" className="flex min-w-0 gap-1 overflow-x-auto [scrollbar-width:none]">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end
              className={({ isActive }) =>
                cn(
                  "flex min-h-11 shrink-0 items-center whitespace-nowrap border-b-2 px-3 text-13 font-semibold",
                  isActive ? "border-brand text-ink" : "border-transparent text-muted hover:text-ink",
                )
              }
            >
              {t.label}
              {counts?.[t.to] ? <span className="num ml-1.5 rounded-full bg-tint-100 px-1.5 text-11 text-brand-deep dark:text-brand-mid">{counts[t.to]}</span> : null}
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  );
}
