import { Fragment, useLayoutEffect, useRef } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { Briefcase, ClipboardList, Filter, Gauge, LayoutDashboard, Logo, Network, ShieldCheck, SlidersHorizontal, type LucideIcon, cn } from "@fsp/ui";

import { ADMIN_GROUPS, type NavItem } from "@/app/routes";
import { activeNav } from "./shell-meta";

/** Пункты меню по группам: сначала без группы («Главная»), затем Очереди · Справочники · Аналитика. */
export function groupNav(nav: NavItem[]): { id: string; label?: string; items: NavItem[] }[] {
  const out: { id: string; label?: string; items: NavItem[] }[] = [{ id: "top", items: nav.filter((n) => !n.group) }];
  for (const g of ADMIN_GROUPS) {
    const items = nav.filter((n) => n.group === g.id);
    if (items.length) out.push({ id: g.id, label: g.label, items });
  }
  return out.filter((g) => g.items.length);
}

/** Иконки пунктов админки: по пути пункта, без изменения маршрутов. */
const ADMIN_ICONS: Record<string, LucideIcon> = {
  "/federation": LayoutDashboard,
  "/admin/families": SlidersHorizontal,
  "/federation/moderation": ShieldCheck,
  "/federation/registry": ClipboardList,
  "/admin/professions": Briefcase,
  "/admin/skills": Network,
  "/federation/funnel": Filter,
  "/federation/analytics": Gauge,
};

const itemClass = (on: boolean) =>
  cn(
    "flex min-h-9 items-center gap-2.5 rounded-lg px-3 text-14 font-semibold",
    on ? "bg-tint-100 text-brand-deep dark:text-brand-mid" : "text-muted hover:bg-tint-50 hover:text-ink",
  );

/** Боковая панель админки ФСП: меню по группам, закреплено при прокрутке. На телефоне — `AdminMobileNav`. */
export function AdminSidebar({ nav }: { nav: NavItem[] }) {
  const current = activeNav(nav, useLocation().pathname);
  return (
    <aside className="hidden border-r border-hairline bg-card p-4 md:sticky md:top-0 md:block md:h-dvh md:self-start md:overflow-y-auto">
      <NavLink to="/federation" aria-label="ФСП Карьера — главная админки" className="mb-6 block">
        <Logo />
      </NavLink>
      <nav aria-label="Разделы" className="flex flex-col gap-4">
        {groupNav(nav).map((g, i) => (
          <div key={g.id} className={cn("flex flex-col gap-1", i > 0 && "border-t border-hairline pt-4")} role="group" aria-label={g.label}>
            {g.label && <p className="px-3 pb-1 text-12 font-semibold uppercase tracking-wider text-muted">{g.label}</p>}
            {g.items.map((n) => {
              const Icon = ADMIN_ICONS[n.to];
              return (
                <Link key={n.to} to={n.to} aria-current={current === n ? "page" : undefined} className={itemClass(current === n)}>
                  {Icon && <Icon aria-hidden className="size-4 shrink-0" />}
                  {n.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}

/** Меню админки на телефоне (< 768 px): строка с горизонтальной прокруткой, группы разделены чертой. */
export function AdminMobileNav({ nav }: { nav: NavItem[] }) {
  const current = activeNav(nav, useLocation().pathname);
  const ref = useRef<HTMLElement>(null);
  // Активный пункт докручиваем в видимую область: иначе на 375 px «где я?» не видно.
  useLayoutEffect(() => {
    const box = ref.current;
    const on = box?.querySelector<HTMLElement>("[aria-current=page]");
    if (!box || !on) return;
    const l = on.offsetLeft - box.offsetLeft;
    const r = l + on.offsetWidth;
    if (l < box.scrollLeft) box.scrollLeft = l - 16;
    else if (r > box.scrollLeft + box.clientWidth) box.scrollLeft = r - box.clientWidth + 16;
  }, [current]);
  return (
    <nav
      ref={ref}
      aria-label="Разделы"
      className="flex gap-1 overflow-x-auto overflow-y-hidden overscroll-x-contain border-b border-hairline bg-card px-4 py-2 [scrollbar-width:none] md:hidden [&::-webkit-scrollbar]:hidden"
    >
      {groupNav(nav).map((g, i) => (
        <Fragment key={g.id}>
          {i > 0 && <span aria-hidden className="mx-1 my-2 w-px shrink-0 bg-hairline" />}
          {g.items.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              aria-current={current === n ? "page" : undefined}
              title={g.label ? `${g.label}: ${n.label}` : n.label}
              className={cn(itemClass(current === n), "min-h-11 shrink-0 whitespace-nowrap")}
            >
              {n.label}
            </Link>
          ))}
        </Fragment>
      ))}
    </nav>
  );
}
