import { expect, test } from "@playwright/test";

/** E39-27: новое задание по шаблону — не больше 5 шагов (кнопок «Дальше»/«Сохранить» после выбора шаблона). */
test("b1: задание по шаблону Backend создаётся за 5 шагов", async ({ page }) => {
  const email = `e39-27-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.fsp.test`;
  await page.goto("/register");
  await page.getByTestId("auth-role-employer").click();
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill("e2e-pass-12345");
  await page.getByTestId("auth-consent-pd").click();
  await page.getByTestId("auth-submit").click();
  await expect(page).toHaveURL(/\/employer$/);

  await page.goto("/employer/tasks");
  await page.getByTestId("tasks-howto").click();
  await page.getByTestId("guide-tpl-backend").click();
  for (let i = 2; i <= 5; i++) {
    await page.getByTestId("guide-next").click();
    await expect(page.getByTestId(`guide-step-${i}`)).toHaveAttribute("aria-current", "step");
  }
  await page.getByTestId("guide-save").click();
  await expect(page.getByTestId("constructor-preview")).toBeVisible();
});
