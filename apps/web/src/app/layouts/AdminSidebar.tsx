import { NavLink } from "react-router-dom";

import { Logo, cn } from "@fsp/ui";

import type { NavItem } from "@/app/routes";
import { isPrefix } from "./shell-meta";

/** Боковая панель админки ФСП (макет F1). */
export function AdminSidebar({ nav }: { nav: NavItem[] }) {
  return (
    <aside className="hidden border-r border-hairline bg-card p-4 md:block">
      <NavLink to="/federation" aria-label="ФСП Карьера — дашборд" className="mb-6 block">
        <Logo />
      </NavLink>
      <nav aria-label="Разделы" className="flex flex-col gap-1">
        {nav.map((n) => (
          <NavLink
            key={n.to}
            to={n.to}
            end={isPrefix(nav, n.to)}
            className={({ isActive }) =>
              cn(
                "flex min-h-9 items-center rounded-lg px-3 text-14 font-semibold",
                isActive ? "bg-tint-100 text-brand-deep dark:text-brand-mid" : "text-muted hover:bg-tint-50 hover:text-ink",
              )
            }
          >
            {n.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
