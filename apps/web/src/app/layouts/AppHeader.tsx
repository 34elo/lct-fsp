import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";

import { AccountMenu, AppBar, BrandMark, Moon, Sun, type ShellLinkProps } from "@fsp/ui";

import type { NavItem } from "@/app/routes";
import { useAuth } from "@/shared/lib/auth";
import { avatarSrc } from "@/shared/lib/avatar";
import { useTheme, type ThemeMode } from "@/shared/lib/theme";
import { ROLE_LABEL, activeNav, initials } from "./shell-meta";

const NEXT: Record<ThemeMode, ThemeMode> = { light: "dark", dark: "light" };
const LABEL: Record<ThemeMode, string> = { light: "Тема: светлая", dark: "Тема: тёмная" };
const ICON = { light: Sun, dark: Moon };

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

const THEME_HINT: Record<ThemeMode, string> = { light: "светлая", dark: "тёмная" };

/** Меню аватара v2 (`.menu`): тема и выход. «Настройки» — у всех ролей (`/settings`). */
function UserMenu() {
  const { me, status, logout } = useAuth();
  const { mode, setMode } = useTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  if (status !== "authenticated" || !me) return null;
  const name = me.company?.name ?? me.email ?? "Профиль";
  return (
    <AccountMenu
      letter={initials(me.email ?? name)}
      src={avatarSrc(me.avatar_url ?? me.company?.logo_url)}
      label={`Меню аккаунта: ${name}, ${ROLE_LABEL[me.role] ?? me.role}`}
      items={[
        { label: "Настройки", onSelect: () => navigate("/settings"), active: pathname === "/settings" },
        { label: "Тема", hint: THEME_HINT[mode], onSelect: () => setMode(NEXT[mode]) },
        { label: "Выйти", separatorBefore: true, danger: true, onSelect: () => void logout() },
      ]}
    />
  );
}

const link = ({ href, className, current, children }: ShellLinkProps) => (
  <Link to={href} className={className} aria-current={current ? "page" : undefined}>
    {children}
  </Link>
);

/** Шапка v2 (`.hd`, docs/design/v2): знак ФСП, 4 пункта со счётчиками, справа аватар с меню. */
export function AppHeader({
  nav,
  counts = {},
  withTabs = true,
  brandFromMd = true,
}: {
  nav: NavItem[];
  /** Счётчики вкладок по пути (`/employer/offers` → 8). */
  counts?: Record<string, number | undefined>;
  withTabs?: boolean;
  /** Показывать знак в шапке с `md`. У админки с боковой панелью знак уже в панели — на десктопе не дублируем. */
  brandFromMd?: boolean;
}) {
  const current = activeNav(nav, useLocation().pathname);
  return (
    <AppBar
      brand={
        <NavLink to="/" aria-label="ФСП Карьера — на главную" className={brandFromMd ? "shrink-0" : "shrink-0 md:hidden"}>
          <BrandMark />
        </NavLink>
      }
      items={withTabs ? nav.map((n) => ({ href: n.to, label: n.label, count: counts[n.to] })) : []}
      isCurrent={(i) => current?.to === i.href}
      renderLink={link}
      navLabel="Разделы"
      aside={
        <>
          <ThemeToggle />
          <UserMenu />
        </>
      }
    />
  );
}
