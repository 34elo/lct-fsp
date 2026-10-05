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

/** Вход через API: access-токен для прямых запросов (в приложении он живёт только в памяти). */
export async function apiLogin(request: APIRequestContext, hero: Hero): Promise<string> {
  const r = await request.post("/api/auth/login", {
    data: { email: HEROES[hero].email, password: DEMO_PASSWORD },
  });
  expect(r.ok(), `вход ${hero}: ${r.status()}`).toBeTruthy();
  return (await r.json()).access_token as string;
}

export const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });

/** Вход через форму /login. */
export async function loginAs(page: Page, hero: Hero): Promise<void> {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(HEROES[hero].email);
  await page.locator('input[type="password"]').fill(DEMO_PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/\/login/);
}
