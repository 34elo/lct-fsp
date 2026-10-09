/**
 * Демо-сценарий против прода (E40-1): только демо-аккаунты — песочницы жюри и герои сида.
 * Реальных пользователей не создаёт и не трогает. Запуск по кнопке (`cd.yml` → workflow_dispatch)
 * или вручную: `E2E_PROD_URL=https://… pnpm e2e e2e/b2-prod-demo.spec.ts`.
 * Без `E2E_PROD_URL` пропускается (в обычном `make e2e` на локальном стенде не идёт).
 */
import { expect, test } from "@playwright/test";

const PROD = process.env.E2E_PROD_URL;

test.describe("prod: демо для жюри", () => {
  test.skip(!PROD, "нужен E2E_PROD_URL (адрес прода)");
  test.use({ baseURL: PROD });
  test.setTimeout(120_000);

  test("два входа жюри получают разные песочницы", async ({ request }) => {
    const enter = async () => {
      const r = await request.post("/api/v1/auth/jury", { data: { role: "candidate" } });
      expect(r.ok(), `вход жюри: ${r.status()}`).toBeTruthy();
      return (await r.json()) as { pair: string; user: { id: string; email: string } };
    };
    const a = await enter();
    const b = await enter();
    expect(a.pair).not.toBe(b.pair);
    expect(a.user.id).not.toBe(b.user.id);
    expect(a.user.email).toMatch(/@demo\.fsp\.test$/);
  });

  test("лендинг → кандидат-жюри → экспресс-тест; работодатель-жюри → поиск", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("jury-candidate").click();
    await expect(page).toHaveURL(/\/me\/assessment/);
    await expect(page.getByTestId("jury-panel")).toBeVisible();

    await page.goto("/");
    const employer = page.getByTestId("jury-employer");
    if (await employer.isVisible()) {
      await employer.click();
      await expect(page).toHaveURL(/\/employer/);
    }
  });

  test("цифры лендинга отдаются (демо в них не входит — проверка в тестах core)", async ({ request }) => {
    const r = await request.get("/api/v1/public/stats");
    expect(r.status()).toBe(200);
    const body = await r.json();
    expect(Object.keys(body).sort()).toEqual(["candidates", "companies", "invitations", "median_days_to_invite"]);
  });
});
