import { Skeleton } from "@fsp/ui";
import { Navigate, useLocation } from "react-router-dom";

import { ConsentsForm } from "@/features/auth/ConsentsForm";
import { authText } from "@/features/auth/text";
import { AuthCard } from "@/features/auth/ui";
import { HOME_BY_ROLE, needsConsent, useAuth } from "@/shared/lib/auth";

/** Шаг «Согласия» после регистрации или входа, если обязательное согласие ещё не выдано. */
export default function Consents() {
  const { me, status, reloadMe } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;

  if (status === "loading")
    return (
      <AuthCard title={authText.consents.title}>
        <Skeleton className="h-16" data-testid="consents-loading" />
      </AuthCard>
    );
  if (status === "anonymous" || !me) return <Navigate to="/login" replace />;
  // Обязательное согласие выдано (в том числе только что): уходим дальше.
  const home = from ?? HOME_BY_ROLE[me.role as keyof typeof HOME_BY_ROLE] ?? "/";
  if (!needsConsent(me)) return <Navigate to={home} replace />;

  return (
    <AuthCard title={authText.consents.title} lead={authText.consents.lead}>
      <ConsentsForm onDone={reloadMe} />
    </AuthCard>
  );
}
