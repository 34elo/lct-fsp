import { Button, Field, FieldInput } from "@fsp/ui";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { authErrorText } from "@/features/auth/errors";
import { authText } from "@/features/auth/text";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { postAuthPath, useAuth } from "@/shared/lib/auth";

const t = authText.login;

export default function Login() {
  const { login, me, status } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // После успешного входа `me` появляется в контексте и страница уводит дальше сама.
  if (status === "authenticated" && me) return <Navigate to={postAuthPath(me, from)} replace state={{ from }} />;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await login(String(f.get("email")).trim(), String(f.get("password")));
    } catch (err) {
      setError(authErrorText(err, t.fallbackError));
      setBusy(false);
    }
  }

  return (
    <AuthCard title={t.title} lead={t.lead}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3" data-testid="auth-login-form">
        <Field label={t.email}>
          <FieldInput name="email" type="email" required autoComplete="email" data-testid="auth-email" />
        </Field>
        <Field label={t.password}>
          <FieldInput name="password" type="password" required autoComplete="current-password" data-testid="auth-password" />
        </Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" size="lg" loading={busy} data-testid="auth-submit">
          {busy ? t.busy : t.submit}
        </Button>
      </form>
      <p className="text-14 text-muted">
        {t.noAccount}{" "}
        <Link to="/register" state={{ from }} className="font-semibold text-brand-fg" data-testid="auth-to-register">
          {t.toRegister}
        </Link>
      </p>
      <p className="text-14 text-muted">{t.botHint}</p>
    </AuthCard>
  );
}
