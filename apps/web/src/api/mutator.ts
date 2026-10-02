import { getAccessToken, setAccessToken } from "@/shared/lib/token";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string | undefined,
    public body: unknown,
  ) {
    super(code ?? `HTTP ${status}`);
  }
}

export type ErrorType<E> = ApiError & { body: E };

let refreshing: Promise<boolean> | null = null;

/** Один общий refresh на все параллельные 401 (cookie `rt`, ротация на сервере). */
export function refreshAccess(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "include" });
      if (!r.ok) return false;
      const data = (await r.json()) as { access_token?: string };
      setAccessToken(data.access_token ?? null);
      return !!data.access_token;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

function send(url: string, init: RequestInit) {
  const headers = new Headers(init.headers);
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_BASE}${url}`, { ...init, headers, credentials: "include" });
}

/**
 * Мутатор orval (fetch-клиент): Bearer, при 401 один refresh и повтор,
 * ошибки приходят как ApiError с машинным `code` из Problem Details.
 * Возвращает `{data, status, headers}`, как ожидают сгенерированные хуки.
 */
export async function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  let res = await send(url, init);
  if (res.status === 401 && !url.startsWith("/auth/") && (await refreshAccess())) {
    res = await send(url, init);
  }
  const text = await res.text();
  const data = text ? (JSON.parse(text) as unknown) : undefined;
  if (!res.ok) throw new ApiError(res.status, (data as { code?: string } | undefined)?.code, data);
  return { data, status: res.status, headers: res.headers } as T;
}
