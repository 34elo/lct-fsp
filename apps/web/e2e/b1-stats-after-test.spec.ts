import { expect, test } from "@playwright/test";

/**
 * E43-5: статистика обычного (не демо) кандидата.
 * 1) Свежий кандидат без теста видит пустое состояние с кнопкой «Пройти тест» (без нулей и ошибок).
 * 2) Кандидат, прошедший тест: плитки «Место» и «Сила», категория в графике и блок «Просмотры профиля»
 *    с полной шкалой и пояснением. Реальный аккаунт с пройденным тестом задаётся E2E_TESTED_EMAIL / E2E_TESTED_PASSWORD
 *    (прохождение теста через UI зависит от банка заданий, поэтому в спеке его не повторяем); без них часть 2 пропускается.
 * Запуск: `pnpm --filter fsp-web e2e -- e2e/b1-stats-after-test.spec.ts` на поднятом стеке (E2E_BASE_URL).
 */
test("b1: свежий кандидат — статистика без теста: пустое состояние", async ({ page }) => {
  const email = `e43-5-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.fsp.test`;
  await page.goto("/register");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill("e2e-pass-12345");
  await page.getByTestId("auth-consent-pd").click();
  await page.getByTestId("auth-submit").click();
  await expect(page).toHaveURL(/\/me\/assessment$/);
  await page.goto("/me/stats");
  await expect(page.getByTestId("stats-empty-action")).toBeVisible();
});

test("b1: кандидат после теста — перцентиль, категория и просмотры с полной шкалой", async ({ page }) => {
  const email = process.env.E2E_TESTED_EMAIL;
  const password = process.env.E2E_TESTED_PASSWORD;
  test.skip(!email || !password, "нужен аккаунт с пройденным тестом (E2E_TESTED_EMAIL / E2E_TESTED_PASSWORD)");
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email!);
  await page.locator('input[type="password"]').fill(password!);
  await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/\/login/);
  await page.goto("/me/stats");
  const tiles = page.getByTestId("stats-tiles");
  await expect(tiles).toContainText(/топ-\d+ %/);
  await expect(page.getByTestId("stats-peers")).toBeVisible();
  const views = page.getByTestId("stats-views");
  await expect(views.locator("[data-level]")).toHaveCount(35);
  await expect(page.getByTestId("stats-views-caption")).not.toBeEmpty();
});
