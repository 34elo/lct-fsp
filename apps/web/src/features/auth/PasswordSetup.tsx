import { Button, Field, FieldInput, Skeleton } from "@fsp/ui";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { usePasswordInitialAuthPasswordInitialPost } from "@/api/endpoints/auth/auth";
import { ApiError } from "@/api/mutator";
import { authText } from "@/features/auth/text";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { postAuthPath, useAuth } from "@/shared/lib/auth";

const t = authText.passwordSetup;

/**
 * Первый вход HR временным паролем от владельца компании (E41-16): свой пароль — обязательный шаг,
 * до него другие экраны закрыты (`RequireRole`), а API отвечает `403 password_change_required`.
 */
export default function PasswordSetup() {
  const { me, status, reloadMe, logout } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const setInitial = usePasswordInitialAuthPasswordInitialPost();
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (status === "loading")
    return (
      <AuthCard title={t.title}>
        <Skeleton className="h-16" />
      </AuthCard>
    );
  if (status === "anonymous" || !me) return <Navigate to="/login" replace />;
  if (!me.must_change_password) return <Navigate to={postAuthPath(me, from)} replace state={{ from }} />;

  const errors = {
    next: next && next.length < 8 ? t.min : undefined,
    again: again && again !== next ? t.mismatch : undefined,
  };
  const ready = next.length >= 8 && again === next;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setError(null);
    try {
      await setInitial.mutateAsync({ data: { new_password: next } });
      await reloadMe(); // флаг снят — страница уведёт дальше сама
    } catch (err) {
      const code = err instanceof ApiError ? (err.status === 429 ? "rate_limited" : err.code) : undefined;
      setError((code && t.errors[code]) || t.errors.fallback!);
    }
  }

  return (
    <AuthCard title={t.title} lead={t.lead}>
      <form onSubmit={(e) => void submit(e)} noValidate className="flex flex-col gap-3" data-testid="password-setup-form">
        <input type="email" name="username" autoComplete="username" value={me.email ?? ""} readOnly hidden />
        <Field label={t.next} hint={t.min} error={errors.next}>
          <FieldInput type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} maxLength={128} data-testid="password-setup-new" />
        </Field>
        <Field label={t.repeat} error={errors.again}>
          <FieldInput type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} maxLength={128} data-testid="password-setup-repeat" />
        </Field>
        {error && <ErrorNote data-testid="password-setup-error">{error}</ErrorNote>}
        <Button type="submit" size="lg" disabled={!ready} loading={setInitial.isPending} data-testid="password-setup-submit">
          {setInitial.isPending ? t.busy : t.submit}
        </Button>
      </form>
      <Button variant="ghost" onClick={() => void logout()} data-testid="password-setup-logout">
        {t.logout}
      </Button>
    </AuthCard>
  );
}
