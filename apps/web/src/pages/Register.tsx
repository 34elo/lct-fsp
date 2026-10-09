import { Button, Checkbox, Field, FieldInput, Label, RadioGroup, RadioGroupItem, cn } from "@fsp/ui";
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
  const state = useLocation().state as { from?: string; role?: SignupRole } | null;
  const from = state?.from;
  // Приглашение в команду компании (E39-24) открывает регистрацию сразу с ролью работодателя.
  const [role, setRole] = useState<SignupRole>(state?.role === "employer" ? "employer" : "candidate");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fresh, setFresh] = useState(false);
  const [consent, setConsent] = useState(false);
  const [needConsent, setNeedConsent] = useState(false);

  // Главный путь (E39-6): обязательное согласие — в самой форме, новый кандидат сразу идёт в поток
  // «направление и навыки → грейд и ожидания → тест», без Главной и без экрана согласий.
  if (status === "authenticated" && me) {
    const next = from ?? (fresh && me.role === "candidate" ? PATH_START : undefined);
    return <Navigate to={postAuthPath(me, next)} replace state={{ from: next }} />;
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (!consent) {
      setNeedConsent(true);
      return;
    }
    setBusy(true);
    setError(null);
    setFresh(true);
    try {
      await register(String(f.get("email")).trim(), String(f.get("password")), role, ["pd_processing"]);
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
        <Label
          htmlFor="register-consent"
          data-testid="auth-consent"
          className={cn(
            "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border p-3",
            consent ? "border-brand bg-tint-50" : "border-hairline bg-card",
          )}
        >
          <Checkbox
            id="register-consent"
            className="mt-0.5"
            checked={consent}
            onCheckedChange={(v) => {
              setConsent(v === true);
              setNeedConsent(false);
            }}
            data-testid="auth-consent-pd"
          />
          <span className="flex flex-col gap-0.5">
            <span className="font-semibold">{t.consent}</span>
            <span className="text-13 font-normal text-muted">
              {t.consentHint}{" "}
              <Link to="/privacy" target="_blank" className="font-semibold text-brand-fg underline">
                {t.consentLink}
              </Link>
            </span>
          </span>
        </Label>
        {needConsent && <ErrorNote data-testid="auth-need-consent">{t.needConsent}</ErrorNote>}
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
