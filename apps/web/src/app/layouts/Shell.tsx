import { NavLink, Outlet } from "react-router-dom";

import { type NavItem } from "@/app/routes";
import { useAuth } from "@/shared/lib/auth";
import { cn } from "@/shared/lib/cn";
import { useTheme, type ThemeMode } from "@/shared/lib/theme";
import { Logo } from "@/shared/brand";
import { Button } from "@/shared/ui/button";

const NEXT: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<ThemeMode, string> = { system: "Тема: системная", light: "Тема: светлая", dark: "Тема: тёмная" };

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  return (
    <Button variant="ghost" size="sm" onClick={() => setMode(NEXT[mode])} aria-label={LABEL[mode]} title={LABEL[mode]}>
      {mode === "dark" ? "Тёмная" : mode === "light" ? "Светлая" : "Авто"}
    </Button>
  );
}

function UserMenu() {
  const { status, logout } = useAuth();
  if (status !== "authenticated") return null;
  return (
    <Button variant="outline" size="sm" onClick={() => void logout()}>
      Выйти
    </Button>
  );
}

const link = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-md px-3 py-2 text-sm font-semibold",
    isActive ? "bg-tint-100 text-brand-deep dark:text-brand-mid" : "text-muted hover:text-ink",
  );

const tab = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-w-0 flex-1 items-center justify-center rounded-md px-1 py-2.5 text-xs font-semibold",
    isActive ? "bg-tint-100 text-brand-deep dark:text-brand-mid" : "text-muted",
  );

/** `end` нужен только пункту, чей путь — префикс другого пункта (`/me` и `/me/offers`). */
const isPrefix = (nav: NavItem[], to: string) => nav.some((o) => o.to !== to && o.to.startsWith(`${to}/`));

/**
 * Каркас по ролям. Кабинеты кандидата и работодателя: верхнее меню на десктопе и нижняя панель
 * на 375 px (`desktopOnly` в неё не попадают); админка — боковая панель.
 */
export function Shell({ nav, variant }: { nav: NavItem[]; variant: "top" | "side" }) {
  return (
    <div className={cn("min-h-dvh bg-page text-ink", variant === "side" && "md:grid md:grid-cols-[220px_1fr]")}>
      {variant === "side" && (
        <aside className="hidden border-r border-hairline bg-card p-4 md:block">
          <Logo className="mb-6" />
          <nav aria-label="Разделы" className="flex flex-col gap-1">
            {nav.map((n) => (
              <NavLink key={n.to} to={n.to} end={isPrefix(nav, n.to)} className={link}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        </aside>
      )}
      <div className="flex min-h-dvh min-w-0 flex-col">
        <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-hairline bg-card px-4 py-3">
          <Logo className={variant === "side" ? "md:hidden" : undefined} />
          {variant === "top" && (
            <nav aria-label="Разделы" className="ml-4 hidden gap-1 md:flex">
              {nav.map((n) => (
                <NavLink key={n.to} to={n.to} end={isPrefix(nav, n.to)} className={link}>
                  {n.label}
                </NavLink>
              ))}
            </nav>
          )}
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <UserMenu />
          </div>
        </header>
        <main className={cn("mx-auto w-full max-w-6xl flex-1 p-4 md:p-6", variant === "top" && "pb-24 md:pb-6")}>
          <Outlet />
        </main>
        {variant === "top" && (
          <nav
            aria-label="Разделы"
            className="fixed inset-x-0 bottom-0 z-10 flex gap-1 border-t border-hairline bg-card px-2 py-1 shadow-sheet md:hidden"
          >
            {nav
              .filter((n) => !n.desktopOnly)
              .map((n) => (
                <NavLink key={n.to} to={n.to} end={isPrefix(nav, n.to)} className={tab}>
                  <span className="truncate">{n.label}</span>
                </NavLink>
              ))}
          </nav>
        )}
      </div>
    </div>
  );
}
