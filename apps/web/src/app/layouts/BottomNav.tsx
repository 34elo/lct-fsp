import { Link, useLocation } from "react-router-dom";

import { TabBar, type ShellLinkProps } from "@fsp/ui";

import type { NavItem } from "@/app/routes";
import { activeNav } from "./shell-meta";

const link = ({ href, className, current, children }: ShellLinkProps) => (
  <Link to={href} className={className} aria-current={current ? "page" : undefined}>
    {children}
  </Link>
);

/** Нижняя панель v2 (`.tb`) — до 768 px, 4 пункта подписью, цель касания 60 px. */
export function BottomNav({ items, all, counts = {} }: { items: NavItem[]; all: NavItem[]; counts?: Record<string, number | undefined> }) {
  const current = activeNav(all, useLocation().pathname);
  return (
    <TabBar
      items={items.map((n) => ({ href: n.to, label: n.label, count: counts[n.to] }))}
      isCurrent={(i) => current?.to === i.href}
      renderLink={link}
      navLabel="Разделы"
    />
  );
}
