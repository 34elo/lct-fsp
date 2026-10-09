import { expect, test } from "@playwright/test";

import { loginAs } from "./fixtures";

/** E39-27: новое задание по шаблону — не больше 5 шагов (кнопок «Дальше»/«Сохранить» после выбора шаблона). */
test("b1: задание по шаблону Backend создаётся за 5 шагов", async ({ page }) => {
  // задание создаётся от имени компании: берём Ольгу из демо-сида (у нового аккаунта компании нет)
  await loginAs(page, "olga");

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
