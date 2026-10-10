import type { AnchorHTMLAttributes } from "react";
import { Link, type LinkProps } from "react-router-dom";

/** Адрес кабинета (E41-7): на корневом домене лендинг, кабинет — на `dashboard.`. Пусто — всё на одном origin. */
export const appBase = (): string => ((import.meta.env.VITE_APP_URL as string | undefined) ?? "").replace(/\/+$/, "");

/** Кабинет живёт на другом origin, чем текущая страница (лендинг на корневом домене). */
export function appIsExternal(): boolean {
  const base = appBase();
  if (!base) return false;
  try {
    return new URL(base).origin !== window.location.origin;
  } catch {
    return false;
  }
}

/** Ссылка на экран кабинета: абсолютная, если кабинет на другом origin, иначе относительная. */
export function appUrl(path: string): string {
  return appIsExternal() ? `${appBase()}${path}` : path;
}

type Props = Omit<LinkProps, "to" | "replace"> & { to: string } & Pick<AnchorHTMLAttributes<HTMLAnchorElement>, "rel">;

/** Ссылка в кабинет: `<Link>` на одном origin, обычный `<a>` на `dashboard.`. Роль регистрации — query `?role=`. */
export function AppLink({ to, state, ...rest }: Props) {
  if (!appIsExternal()) return <Link to={to} state={state} {...rest} />;
  let href = appUrl(to);
  const role = (state as { role?: string } | null | undefined)?.role;
  if (role) href += `${href.includes("?") ? "&" : "?"}role=${role}`;
  return <a href={href} {...(rest as AnchorHTMLAttributes<HTMLAnchorElement>)} />;
}
