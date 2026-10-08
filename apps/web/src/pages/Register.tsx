import { Button, Field, FieldInput, Label, RadioGroup, RadioGroupItem, cn } from "@fsp/ui";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { authErrorText } from "@/features/auth/errors";
import { authText } from "@/features/auth/text";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { PATH_START } from "@/features/assessment/model";
import { postAuthPath, useAuth } from "@/shared/lib/auth";

const t = authText.register;

type SignupRole = "candidate" | "employer";
const ROLES: SignupRole[] = ["candidate", "employer"];

export default function Register() {
  const { register, me, status } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [role, setRole] = useState<SignupRole>("candidate");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState(false);

  // Главный путь (E35-2a): новый кандидат после согласий идёт в опрос, а не на пустую Главную.
  if (status === "authenticated" && me) {
    const next = from ?? (fresh && me.role === "candidate" ? PATH_START : undefined);
    return <Navigate to={postAuthPath(me, next)} replace state={{ from: next }} />;
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    setFresh(true);
    try {
      await register(String(f.get("email")).trim(), String(f.get("password")), role);
    } catch (err) {
      setError(authErrorText(err, t.fallbackError, { credentials: false }));
      setBusy(false);
    }
  }

  return (
    <AuthCard title={t.title} lead={t.lead}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3" data-testid="auth-register-form">
        <div className="flex flex-col gap-1.5">
          <span id="role-legend" className="text-13 font-medium">
            {t.role}
          </span>
          <RadioGroup value={role} onValueChange={(v) => setRole(v as SignupRole)} aria-labelledby="role-legend">
            {ROLES.map((r) => (
              <Label
                key={r}
                htmlFor={`role-${r}`}
                data-testid={`auth-role-${r}`}
                className={cn(
                  "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border px-3 py-2",
                  role === r ? "border-brand bg-tint-50" : "border-hairline bg-card",
                )}
              >
                <RadioGroupItem id={`role-${r}`} value={r} className="mt-0.5" />
                <span className="flex flex-col">
                  <span className="font-semibold">{t.roles[r].title}</span>
                  <span className="text-14 font-normal text-muted">{t.roles[r].hint}</span>
                </span>
              </Label>
            ))}
          </RadioGroup>
        </div>
        <Field label={t.email}>
          <FieldInput name="email" type="email" required autoComplete="email" maxLength={254} data-testid="auth-email" />
        </Field>
        <Field label={t.password} hint={t.passwordHint}>
          <FieldInput
            name="password"
            type="password"
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            data-testid="auth-password"
          />
        </Field>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" size="lg" loading={busy} data-testid="auth-submit">
          {busy ? t.busy : t.submit}
        </Button>
      </form>
      <p className="text-14 text-muted">
        {t.haveAccount}{" "}
        <Link to="/login" state={{ from }} className="font-semibold text-brand-fg" data-testid="auth-to-login">
          {t.toLogin}
        </Link>
      </p>
    </AuthCard>
  );
}
