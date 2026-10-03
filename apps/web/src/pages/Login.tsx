import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { authErrorText } from "@/features/auth/errors";
import { AuthCard, ErrorNote, fieldClass } from "@/features/auth/ui";
import { postAuthPath, useAuth } from "@/shared/lib/auth";
import { Button } from "@/shared/ui/button";

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
      setError(authErrorText(err, "Не удалось войти, попробуйте позже"));
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Вход" lead="Профиль, офферы и доказательства навыков — в одном месте.">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Почта
          <input name="email" type="email" required autoComplete="email" className={fieldClass} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Пароль
          <input name="password" type="password" required autoComplete="current-password" className={fieldClass} />
        </label>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" disabled={busy}>
          {busy ? "Входим…" : "Войти"}
        </Button>
      </form>
      <p className="text-sm text-muted">
        Нет аккаунта?{" "}
        <Link to="/register" state={{ from }} className="font-semibold text-brand-fg">
          Зарегистрироваться
        </Link>
      </p>
      <p className="text-sm text-muted">Если вы уже пользуетесь ботом в Telegram, войти можно кнопкой из бота.</p>
    </AuthCard>
  );
}
