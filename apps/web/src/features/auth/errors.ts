import { ApiError } from "@/api/mutator";

/** Русский текст по машинному `code` Problem Details (api.md, коды `/auth/*`). */
export function authErrorText(err: unknown, fallback: string, opts: { credentials?: boolean } = {}): string {
  if (!(err instanceof ApiError)) return fallback;
  switch (err.code) {
    case "invalid_credentials":
      if (opts.credentials === false) return fallback;
      return "Неверная почта или пароль";
    case "email_taken":
      return "Эта почта уже зарегистрирована. Попробуйте войти";
    case "rate_limited":
      return "Слишком много попыток. Подождите минуту";
    case "invalid_magic_token":
      return "Ссылка недействительна или уже использована";
    case "temp_password_expired":
      return "Временный пароль истёк. Попросите владельца компании выдать новый";
  }
  if (err.status === 429) return "Слишком много попыток. Подождите минуту";
  // 401 без кода на регистрации (например, из /me после неё) — не «неверный пароль» (E35-7a).
  if (err.status === 401 && opts.credentials !== false) return "Неверная почта или пароль";
  return fallback;
}

/** `redirect` из ссылки бота: только путь внутри SPA, иначе игнорируем (защита от open redirect). */
export function safeRedirect(raw: string | null): string | undefined {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return undefined;
  return raw;
}

/** Секунд до конца кулдауна из `detail` (ISO-дата) ответа 409 `cooldown`; без даты — минута. */
export function cooldownSeconds(err: unknown, now = Date.now()): number {
  const detail = err instanceof ApiError ? (err.body as { detail?: unknown } | undefined)?.detail : undefined;
  const at = typeof detail === "string" ? Date.parse(detail) : NaN;
  const sec = Number.isNaN(at) ? 60 : Math.ceil((at - now) / 1000);
  return Math.max(1, Math.min(sec, 3600));
}

/** Русский текст ошибок подтверждения почты (`/auth/email/send|verify`). */
export function verifyErrorText(err: unknown, texts: Record<string, string>): string {
  if (err instanceof ApiError) {
    if (err.code && err.code in texts && err.code !== "fallback") return texts[err.code]!;
    if (err.status === 409) return texts.cooldown!;
    if (err.status === 429) return err.code === "too_many_attempts" ? texts.too_many_attempts! : texts.rate_limited!;
  }
  return texts.fallback!;
}
