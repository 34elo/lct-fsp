import { Fragment, type ReactNode } from "react";

import { cn } from "../lib/cn";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../primitives/overlay";

/* Каркас v2: шапка `.hd` (десктоп), компактная шапка `.mh` + нижняя панель `.tb` (телефон), меню аватара `.menu`.
   Пакет не зависит от роутера: ссылки рисует `renderLink` приложения. */

export interface ShellNavItem {
  href: string;
  label: string;
  /** Счётчик `.ct` (приглашения). Ноль и undefined не показываем. */
  count?: number;
}

export interface ShellLinkProps {
  href: string;
  className: string;
  current: boolean;
  children: ReactNode;
}

export type RenderShellLink = (p: ShellLinkProps) => ReactNode;

const defaultLink: RenderShellLink = ({ href, className, current, children }) => (
  <a href={href} className={className} aria-current={current ? "page" : undefined}>
    {children}
  </a>
);

/** Счётчик `.ct`. */
export function NavCount({ value, className }: { value?: number; className?: string }) {
  if (!value) return null;
  return (
    <span className={cn("ml-1.5 rounded-[10px] bg-tint-100 px-[7px] py-[3px] font-mono text-11 leading-none font-semibold text-chip-fg", className)}>
      {value}
    </span>
  );
}

/** Знак ФСП `.brand`: картинка 28 px и «ФСП» Mono 700. `src` — путь к знаку в приложении. */
export function BrandMark({ src = "/brand/logo_02.svg", text = "ФСП", className }: { src?: string; text?: string; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2 font-mono text-[18px] font-bold text-brand-deep dark:text-ink", className)}>
      <img src={src} alt="" className="block size-7" />
      {text}
    </span>
  );
}

/** Аватар `.av`: квадрат 32 px с буквой. В тёмной теме — brand. */
export function AvatarButtonFace({ letter }: { letter: string }) {
  return (
    <span aria-hidden className="grid size-8 flex-none place-items-center rounded-lg bg-ink font-mono text-12 font-bold text-on-brand dark:bg-brand">
      {letter.slice(0, 1).toUpperCase() || "?"}
    </span>
  );
}

export interface AccountMenuItem {
  label: string;
  onSelect: () => void;
  /** Справа мелко: «светлая». */
  hint?: ReactNode;
  /** Текущий раздел (`.menu a.on`). */
  active?: boolean;
  /** Разделитель перед пунктом («Выйти»). */
  separatorBefore?: boolean;
  /** Разрушающее действие («Выйти»): красный текст. */
  danger?: boolean;
}

/** Меню аватара: «Настройки», «Тема · светлая», разделитель, «Выйти». Пункты передаёт приложение. */
export function AccountMenu({
  letter,
  items,
  label = "Меню аккаунта",
  className,
}: {
  letter: string;
  items: AccountMenuItem[];
  label?: string;
  className?: string;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" aria-label={label} className={cn("grid min-h-11 min-w-11 place-items-center rounded-lg sm:min-h-9 sm:min-w-9", className)}>
          <AvatarButtonFace letter={letter} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52 rounded-xl p-1.5 shadow-menu">
        {items.map((it) => (
          <Fragment key={it.label}>
            {it.separatorBefore && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onSelect={it.onSelect}
              className={cn("justify-between rounded-lg px-2.5 font-medium sm:min-h-[38px]", it.active && "bg-tint-50 font-semibold", it.danger && "text-error focus:text-error")}
            >
              {it.label}
              {it.hint && <span className="num text-12 font-normal text-muted">{it.hint}</span>}
            </DropdownMenuItem>
          </Fragment>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Шапка `.hd`: знак, меню из пунктов (активный — подчёркивание brand), справа `aside` (аватар). */
export function AppBar({
  brand,
  items,
  isCurrent,
  renderLink = defaultLink,
  aside,
  navLabel = "Основное меню",
  className,
}: {
  brand?: ReactNode;
  items: ShellNavItem[];
  isCurrent: (item: ShellNavItem) => boolean;
  renderLink?: RenderShellLink;
  aside?: ReactNode;
  navLabel?: string;
  className?: string;
}) {
  return (
    <header className={cn("sticky top-0 z-20 border-b border-hairline bg-card", className)}>
      <div className="mx-auto flex h-14 w-full max-w-[1328px] min-w-0 items-center gap-7 px-4 md:px-6">
        {brand ?? <BrandMark />}
        {items.length > 0 && (
          <nav aria-label={navLabel} className="hidden h-full min-w-0 items-stretch overflow-x-auto md:flex [scrollbar-width:none]">
            {items.map((n) => {
              const current = isCurrent(n);
              return (
                <Fragment key={n.href}>
                  {renderLink({
                    href: n.href,
                    current,
                    className: cn(
                      "flex h-full shrink-0 items-center px-3 whitespace-nowrap",
                      current ? "font-semibold text-ink shadow-[inset_0_-2px_0_var(--brand)]" : "font-medium text-muted hover:text-ink",
                    ),
                    children: (
                      <>
                        {n.label}
                        <NavCount value={n.count} />
                      </>
                    ),
                  })}
                </Fragment>
              );
            })}
          </nav>
        )}
        <div className="ml-auto flex items-center gap-1">{aside}</div>
      </div>
    </header>
  );
}

/** Нижняя панель `.tb` (телефон): 4 пункта подписью, активный — brand и полоса сверху. */
export function TabBar({
  items,
  isCurrent,
  renderLink = defaultLink,
  navLabel = "Основное меню",
  className,
}: {
  items: ShellNavItem[];
  isCurrent: (item: ShellNavItem) => boolean;
  renderLink?: RenderShellLink;
  navLabel?: string;
  className?: string;
}) {
  return (
    <nav
      aria-label={navLabel}
      className={cn(
        "fixed inset-x-0 bottom-0 z-20 grid min-h-[60px] border-t border-hairline bg-card pb-[env(safe-area-inset-bottom)] md:hidden",
        className,
      )}
      style={{ gridTemplateColumns: `repeat(${Math.max(1, items.length)}, minmax(0, 1fr))` }}
    >
      {items.map((n) => {
        const current = isCurrent(n);
        return (
          <Fragment key={n.href}>
            {renderLink({
              href: n.href,
              current,
              className: cn(
                "relative flex min-h-[60px] min-w-0 items-center justify-center px-1 text-center text-12",
                current ? "font-bold text-brand-fg shadow-[inset_0_2px_0_var(--brand)]" : "font-medium text-muted",
              ),
              children: (
                <>
                  <span className="truncate">{n.label}</span>
                  <NavCount value={n.count} className="absolute top-2 right-1.5 m-0" />
                </>
              ),
            })}
          </Fragment>
        );
      })}
    </nav>
  );
}
