import { Skeleton } from "@fsp/ui";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { authErrorText, safeRedirect } from "@/features/auth/errors";
import { authText } from "@/features/auth/text";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { postAuthPath, useAuth } from "@/shared/lib/auth";

const t = authText.magic;

/** `/auth/magic?token=…&redirect=/…` — вход по одноразовой ссылке из Telegram-бота. */
export default function MagicLogin() {
  const { loginWithMagic, me, status } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token");
  const redirect = safeRedirect(params.get("redirect"));
  const [error, setError] = useState<string | null>(token ? null : t.noToken);
  const started = useRef(false);

  useEffect(() => {
    // Токен одноразовый: повторный запрос (StrictMode, перерисовка) его сожжёт.
    if (!token || status === "loading" || started.current) return;
    if (status === "authenticated") return;
    started.current = true;
    loginWithMagic(token).catch((err) => setError(authErrorText(err, t.fallbackError)));
  }, [token, status, loginWithMagic]);

  if (status === "authenticated" && me) return <Navigate to={postAuthPath(me, redirect)} replace state={{ from: redirect }} />;

  return (
    <AuthCard title={t.title}>
      {error ? (
        <>
          <ErrorNote data-testid="auth-magic-error">{error}</ErrorNote>
          <p className="text-sm text-muted">
            {t.retryPrefix}{" "}
            <Link to="/login" className="font-semibold text-brand-fg">
              {t.toLogin}
            </Link>
            .
          </p>
        </>
      ) : (
        <div className="flex flex-col gap-2" data-testid="auth-magic-busy">
          <Skeleton className="h-4 w-2/3" aria-label={t.busy} />
          <Skeleton className="h-4 w-1/2" aria-label={t.busy} />
        </div>
      )}
    </AuthCard>
  );
}
