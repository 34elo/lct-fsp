/** Сквозной сценарий: Аня → тест → категория → Ольга → оффер. */
import { expect, test } from "@playwright/test";
import { loginAs } from "./fixtures";

test.setTimeout(120_000); // loginAs при лимите входа ждёт окно

test("лендинг открывается, вход Ани уводит с /login", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).not.toBeEmpty();
  await loginAs(page, "anya");
});
