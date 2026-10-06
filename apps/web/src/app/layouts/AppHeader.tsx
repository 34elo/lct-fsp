import { NavLink } from "react-router-dom";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  LogOut,
  Logo,
  Moon,
  Sun,
  SunMoon,
  cn,
} from "@fsp/ui";

import type { NavItem } from "@/app/routes";
import { useAuth } from "@/shared/lib/auth";
import { useTheme, type ThemeMode } from "@/shared/lib/theme";
import { PageContainer } from "./PageContainer";
import { ROLE_LABEL, initials, isPrefix } from "./shell-meta";

const NEXT: Record<ThemeMode, ThemeMode> = { light: "dark", dark: "system", system: "light" };
const LABEL: Record<ThemeMode, string> = { system: "Тема: системная", light: "Тема: светлая", dark: "Тема: тёмная" };
const ICON = { light: Sun, dark: Moon, system: SunMoon };

export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const Icon = ICON[mode];
  return (
    <button
      type="button"
      onClick={() => setMode(NEXT[mode])}
      aria-label={LABEL[mode]}
      title={LABEL[mode]}
      className="grid size-11 place-items-center rounded-lg text-muted hover:bg-tint-50 hover:text-ink sm:size-9"
    >
      <Icon className="size-4" aria-hidden />
    </button>
  );
}

function UserMenu() {
  const { me, status, logout } = useAuth();
  const { mode, setMode } = useTheme();
  if (status !== "authenticated" || !me) return null;
  const name = me.email ?? "Профиль";
  const ThemeIcon = ICON[mode];
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Меню пользователя"
          className="flex min-h-11 items-center gap-2 rounded-lg px-1 hover:bg-tint-50 sm:min-h-9"
        >
          <span className="hidden min-w-0 text-right leading-tight md:block">
            <span className="block max-w-48 truncate text-13 font-semibold">{me.company?.name ?? name}</span>
            <span className="block text-12 text-muted">
              {me.company ? `${name} · ` : ""}
              {ROLE_LABEL[me.role] ?? me.role}
            </span>
          </span>
          <span aria-hidden className="grid size-9 place-items-center rounded-lg bg-tint-100 font-mono text-13 font-bold text-brand-deep dark:text-brand-mid">{initials(name)}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => setMode(NEXT[mode])}>
          <ThemeIcon className="size-4" aria-hidden /> {LABEL[mode]}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void logout()}>
          <LogOut className="size-4" aria-hidden /> Выйти
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const tab = ({ isActive }: { isActive: boolean }) =>
  cn(
    "relative flex h-14 shrink-0 items-center gap-1.5 whitespace-nowrap px-3 text-14 font-semibold",
    isActive
      ? "text-ink after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-brand"
      : "text-muted hover:text-ink",
  );

/** Шапка по макету A: логотип, вкладки со счётчиками, справа пользователь и меню. */
export function AppHeader({
  nav,
  counts = {},
  withTabs = true,
}: {
  nav: NavItem[];
  /** Счётчики вкладок по пути (`/employer/offers` → 8). */
  counts?: Record<string, number | undefined>;
  withTabs?: boolean;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-hairline bg-card">
      <PageContainer className="flex h-14 min-w-0 items-center gap-3">
        <NavLink to="/" aria-label="ФСП Карьера — на главную" className="shrink-0">
          <Logo />
        </NavLink>
        {withTabs && (
          <nav aria-label="Разделы" className="ml-4 hidden min-w-0 items-stretch overflow-x-auto md:flex [scrollbar-width:none]">
            {nav.map((n) => (
              <NavLink key={n.to} to={n.to} end={isPrefix(nav, n.to)} className={tab}>
                {n.label}
                {counts[n.to] !== undefined && (
                  <span className="rounded-full bg-tint-100 px-1.5 font-mono text-12 text-brand-fg">{counts[n.to]}</span>
                )}
              </NavLink>
            ))}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <UserMenu />
        </div>
      </PageContainer>
    </header>
  );
}
