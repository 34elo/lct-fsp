import { Link, useLocation } from "react-router-dom";

import { cn } from "@fsp/ui";

import type { NavItem } from "@/app/routes";
import { BOTTOM_ICON, activeNav } from "./shell-meta";

/** Нижняя навигация кандидата — до 768 px, иконка и подпись, цель касания ≥ 44 px. */
export function BottomNav({ items, all }: { items: NavItem[]; all: NavItem[] }) {
  const current = activeNav(all, useLocation().pathname);
  return (
    <nav
      aria-label="Разделы"
      className="fixed inset-x-0 bottom-0 z-20 flex border-t border-hairline bg-card pb-[env(safe-area-inset-bottom)] shadow-sheet md:hidden"
    >
      {items.map((n) => {
        const Icon = BOTTOM_ICON[n.to];
        const active = current?.to === n.to;
        return (
          <Link
            key={n.to}
            to={n.to}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex min-h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-12 font-semibold",
              active ? "text-brand-fg" : "text-muted",
            )}
          >
            {Icon && <Icon className="size-5" aria-hidden />}
            <span className="truncate">{n.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
