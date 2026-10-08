import { useEffect } from "react";
import { matchPath, useLocation } from "react-router-dom";

import { ROUTES } from "@/app/routes";

export const APP_TITLE = "ФСП Карьера";

/** Заголовок вкладки по экрану: «Настройки · ФСП Карьера». Нет маршрута в карте — просто название продукта. */
export function titleFor(pathname: string): string {
  if (pathname === "/") return APP_TITLE;
  const hit = ROUTES.find((r) => !r.redirect && matchPath({ path: r.path, end: true }, pathname));
  return hit ? `${hit.title} · ${APP_TITLE}` : APP_TITLE;
}

export function DocumentTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = titleFor(pathname);
  }, [pathname]);
  return null;
}
