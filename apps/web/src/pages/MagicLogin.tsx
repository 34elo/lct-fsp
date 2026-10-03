import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";

import { authErrorText, safeRedirect } from "@/features/auth/errors";
import { AuthCard, ErrorNote } from "@/features/auth/ui";
import { postAuthPath, useAuth } from "@/shared/lib/auth";

/** `/auth/magic?token=…&redirect=/…` — вход по одноразовой ссылке из Telegram-бота. */
export default function MagicLogin() {
  const { loginWithMagic, me, status } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token");
  const redirect = safeRedirect(params.get("redirect"));
  const [error, setError] = useState<string | null>(token ? null : "В ссылке нет токена");
  const started = useRef(false);

  useEffect(() => {
    // Токен одноразовый: повторный запрос (StrictMode, перерисовка) его сожжёт.
    if (!token || status === "loading" || started.current) return;
    if (status === "authenticated") return;
    started.current = true;
    loginWithMagic(token).catch((err) => setError(authErrorText(err, "Не удалось войти по ссылке, попробуйте позже")));
  }, [token, status, loginWithMagic]);

  if (status === "authenticated" && me) return <Navigate to={postAuthPath(me, redirect)} replace state={{ from: redirect }} />;

  return (
    <AuthCard title="Вход по ссылке">
      {error ? (
        <>
          <ErrorNote>{error}</ErrorNote>
          <p className="text-sm text-muted">
            Запросите новую ссылку в боте или{" "}
            <Link to="/login" className="font-semibold text-brand-fg">
              войдите по почте
            </Link>
            .
          </p>
        </>
      ) : (
        <p role="status" className="text-sm text-muted">
          Входим…
        </p>
      )}
    </AuthCard>
  );
}
