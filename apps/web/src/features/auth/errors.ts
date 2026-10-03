import { ApiError } from "@/api/mutator";

/** Русский текст по машинному `code` Problem Details (api.md, коды `/auth/*`). */
export function authErrorText(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  switch (err.code) {
    case "invalid_credentials":
      return "Неверная почта или пароль";
    case "email_taken":
      return "Эта почта уже зарегистрирована. Попробуйте войти";
    case "rate_limited":
      return "Слишком много попыток. Подождите минуту";
    case "invalid_magic_token":
      return "Ссылка недействительна или уже использована";
  }
  if (err.status === 429) return "Слишком много попыток. Подождите минуту";
  if (err.status === 401) return "Неверная почта или пароль";
  return fallback;
}

/** `redirect` из ссылки бота: только путь внутри SPA, иначе игнорируем (защита от open redirect). */
export function safeRedirect(raw: string | null): string | undefined {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\")) return undefined;
  return raw;
}
