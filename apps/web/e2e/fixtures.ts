/** Общий харнесс e2e: герои демо-сида (tools/seed/config.yaml, heroes/*.yaml) и вход. */
import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Тестовый пароль всех демо-аккаунтов — `tools/seed/config.yaml` (seed.password). */
export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "demo-pass-1234";

export const HEROES = {
  anya: { email: "anya@demo.fsp.test", role: "candidate" },
  dima: { email: "dima@demo.fsp.test", role: "candidate" },
  olga: { email: "olga@demo.fsp.test", role: "employer" },
} as const;
export type Hero = keyof typeof HEROES;

const tokens = new Map<Hero, string>();

/**
 * Вход через API: access-токен для прямых запросов (в приложении он живёт только в памяти).
 * Токен кешируется на процесс: лимит входа на сервере — 5 в минуту на email, а спеков много.
 */
export async function apiLogin(request: APIRequestContext, hero: Hero): Promise<string> {
  const cached = tokens.get(hero);
  if (cached) return cached;
  let r = await request.post("/api/v1/auth/login", { data: { email: HEROES[hero].email, password: DEMO_PASSWORD } });
  for (let i = 0; i < 4 && r.status() === 429; i++) {
    await new Promise((res) => setTimeout(res, 20_000)); // лимит входа — ждём окно
    r = await request.post("/api/v1/auth/login", { data: { email: HEROES[hero].email, password: DEMO_PASSWORD } });
  }
  expect(r.ok(), `вход ${hero}: ${r.status()}`).toBeTruthy();
  const token = (await r.json()).access_token as string;
  tokens.set(hero, token);
  return token;
}

export const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

/**
 * Вход через форму /login. Лимит входа на сервере — 5 в минуту на email и 10 на IP: полный прогон
 * может его упереть, поэтому при отказе ждём окно и пробуем снова (до 4 раз).
 */
export async function loginAs(page: Page, hero: Hero): Promise<void> {
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(HEROES[hero].email);
    await page.locator('input[type="password"]').fill(DEMO_PASSWORD);
    await page.keyboard.press("Enter");
    const left = await expect(page).not.toHaveURL(/\/login/, { timeout: 8_000 }).then(() => true, () => false);
    if (left) return;
    await page.waitForTimeout(20_000);
  }
  await expect(page).not.toHaveURL(/\/login/);
}
