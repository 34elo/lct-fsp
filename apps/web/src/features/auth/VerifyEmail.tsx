import { Button, Field, FieldInput } from "@fsp/ui";
import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { useEmailSendAuthEmailSendPost, useEmailVerifyAuthEmailVerifyPost } from "@/api/endpoints/auth/auth";
import { cooldownSeconds, verifyErrorText } from "@/features/auth/errors";
import { authText } from "@/features/auth/text";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { HOME_BY_ROLE, useAuth, type Role } from "@/shared/lib/auth";

const t = authText.verify;

export default function VerifyEmail() {
  const { me, status, reloadMe } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [left, setLeft] = useState(0);
  const [done, setDone] = useState(false);
  const verify = useEmailVerifyAuthEmailVerifyPost();
  const send = useEmailSendAuthEmailSendPost();

  useEffect(() => {
    if (left <= 0) return;
    const id = setTimeout(() => setLeft((n) => n - 1), 1000);
    return () => clearTimeout(id);
  }, [left]);

  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: "/verify-email" }} />;
  const home = from ?? HOME_BY_ROLE[(me?.role as Role | undefined) ?? "candidate"] ?? "/";

  if (done || (me?.email_verified && status === "authenticated")) {
    return (
      <AuthCard title={done ? t.done : t.already}>
        <Link to={home} className="inline-flex min-h-11 items-center font-semibold text-brand-fg" data-testid="verify-continue">
          {t.continue}
        </Link>
      </AuthCard>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInfo(null);
    try {
      await verify.mutateAsync({ data: { code: code.trim() } });
      setDone(true);
      await reloadMe().catch(() => undefined);
    } catch (err) {
      setError(verifyErrorText(err, t.errors));
    }
  }

  async function onResend() {
    setError(null);
    setInfo(null);
    try {
      await send.mutateAsync();
      setInfo(t.resendSent);
      setLeft(60);
      setCode("");
    } catch (err) {
      setError(verifyErrorText(err, t.errors));
      if ((err as { status?: number }).status === 409) setLeft(cooldownSeconds(err));
    }
  }

  return (
    <AuthCard title={t.title} lead={t.lead}>
      <form onSubmit={onSubmit} className="flex flex-col gap-3" data-testid="verify-form">
        <Field label={t.code}>
          <FieldInput
            name="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            data-testid="verify-code"
          />
        </Field>
        {error && <ErrorNote data-testid="verify-error">{error}</ErrorNote>}
        {info && (
          <p role="status" className="text-14 text-muted" data-testid="verify-info">
            {info}
          </p>
        )}
        <Button type="submit" size="lg" loading={verify.isPending} disabled={code.length < 6} data-testid="verify-submit">
          {verify.isPending ? t.busy : t.submit}
        </Button>
      </form>
      <Button type="button" variant="outline" loading={send.isPending} disabled={left > 0} onClick={onResend} data-testid="verify-resend">
        {left > 0 ? `${t.resendIn} ${left} с` : t.resend}
      </Button>
    </AuthCard>
  );
}
