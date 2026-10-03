import { Navigate, useLocation } from "react-router-dom";

import { ConsentsForm } from "@/features/auth/ConsentsForm";
import { AuthCard } from "@/features/auth/ui";
import { HOME_BY_ROLE, needsConsent, useAuth } from "@/shared/lib/auth";

/** Шаг «Согласия» после регистрации или входа, если обязательное согласие ещё не выдано. */
export default function Consents() {
  const { me, status, reloadMe } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;

  if (status === "loading") return <p role="status" className="p-6 text-muted">Загрузка…</p>;
  if (status === "anonymous" || !me) return <Navigate to="/login" replace />;
  // Обязательное согласие выдано (в том числе только что): уходим дальше.
  const home = from ?? HOME_BY_ROLE[me.role as keyof typeof HOME_BY_ROLE] ?? "/";
  if (!needsConsent(me)) return <Navigate to={home} replace />;

  return (
    <AuthCard title="Согласия" lead="Каждое согласие даётся отдельно, отозвать его можно в настройках.">
      <ConsentsForm
        onDone={reloadMe}
      />
    </AuthCard>
  );
}
