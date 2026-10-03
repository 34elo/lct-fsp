import { Navigate, Outlet, useLocation } from "react-router-dom";

import { HOME_BY_ROLE, needsConsent, useAuth, type Role } from "@/shared/lib/auth";

export function RequireRole({ role }: { role: Role }) {
  const { status, role: mine, me } = useAuth();
  const loc = useLocation();
  if (status === "loading") return <p role="status" className="p-6 text-muted">Загрузка…</p>;
  if (status === "anonymous" || !mine) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  if (me && needsConsent(me)) return <Navigate to="/consents" replace state={{ from: loc.pathname }} />;
  if (mine !== role) return <Navigate to={HOME_BY_ROLE[mine]} replace />;
  return <Outlet />;
}
