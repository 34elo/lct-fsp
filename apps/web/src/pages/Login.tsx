import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/mutator";
import { HOME_BY_ROLE, useAuth } from "@/shared/lib/auth";
import { Button } from "@/shared/ui/button";

const field = "h-11 rounded-lg border border-hairline bg-card px-3 text-ink";

export default function Login() {
  const { login, role, status } = useAuth();
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated" && role) return <Navigate to={from ?? HOME_BY_ROLE[role]} replace />;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await login(String(f.get("email")), String(f.get("password")));
      nav(from ?? "/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? "Неверная почта или пароль" : "Не удалось войти, попробуйте позже");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mx-auto flex max-w-sm flex-col gap-3">
      <h1 className="text-2xl font-bold">Вход</h1>
      <label className="flex flex-col gap-1 text-sm">
        Почта
        <input name="email" type="email" required autoComplete="email" className={field} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Пароль
        <input name="password" type="password" required autoComplete="current-password" className={field} />
      </label>
      {error && (
        <p role="alert" className="rounded-lg bg-error-bg px-3 py-2 text-sm text-error">
          {error}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        Войти
      </Button>
    </form>
  );
}
