import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";

import { authErrorText } from "@/features/auth/errors";
import { AuthCard, ErrorNote, fieldClass } from "@/features/auth/ui";
import { postAuthPath, useAuth } from "@/shared/lib/auth";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/button";

type SignupRole = "candidate" | "employer";

const ROLES: { value: SignupRole; title: string; hint: string }[] = [
  { value: "candidate", title: "Я ищу работу", hint: "Собрать профиль из доказательств" },
  { value: "employer", title: "Я ищу людей", hint: "Искать проверенных кандидатов" },
];

export default function Register() {
  const { register, me, status } = useAuth();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const [role, setRole] = useState<SignupRole>("candidate");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "authenticated" && me) return <Navigate to={postAuthPath(me, from)} replace state={{ from }} />;

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await register(String(f.get("email")).trim(), String(f.get("password")), role);
    } catch (err) {
      setError(authErrorText(err, "Не удалось зарегистрироваться, попробуйте позже"));
      setBusy(false);
    }
  }

  return (
    <AuthCard title="Регистрация" lead="Дальше попросим согласия на обработку данных — каждое отдельно.">
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-sm">Кто вы</legend>
          {ROLES.map((r) => (
            <label
              key={r.value}
              className={cn(
                "flex cursor-pointer flex-col rounded-lg border px-3 py-2 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand",
                role === r.value ? "border-brand bg-tint-50" : "border-hairline bg-card",
              )}
            >
              <input
                type="radio"
                name="role"
                value={r.value}
                checked={role === r.value}
                onChange={() => setRole(r.value)}
                className="sr-only"
              />
              <span className="font-semibold">{r.title}</span>
              <span className="text-sm text-muted">{r.hint}</span>
            </label>
          ))}
        </fieldset>
        <label className="flex flex-col gap-1 text-sm">
          Почта
          <input name="email" type="email" required autoComplete="email" maxLength={254} className={fieldClass} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Пароль
          <input
            name="password"
            type="password"
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            aria-describedby="pw-hint"
            className={fieldClass}
          />
          <span id="pw-hint" className="text-xs text-muted">
            Не короче 8 символов
          </span>
        </label>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button type="submit" disabled={busy}>
          {busy ? "Создаём…" : "Создать аккаунт"}
        </Button>
      </form>
      <p className="text-sm text-muted">
        Уже есть аккаунт?{" "}
        <Link to="/login" state={{ from }} className="font-semibold text-brand">
          Войти
        </Link>
      </p>
    </AuthCard>
  );
}
