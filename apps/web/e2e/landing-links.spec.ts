import { expect, test } from "@playwright/test";

/** Кнопки лендинга ведут туда, что на них написано, и не на Главную без входа. */

test("«Пройти тест» открывает регистрацию кандидата", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Пройти тест" }).first().click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.locator("#role-candidate")).toBeChecked();
});

test("«Ищу сотрудников» открывает регистрацию компании", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Ищу сотрудников" }).first().click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.locator("#role-employer")).toBeChecked();
});

test("«Войти» и подвал ведут на свои экраны", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Войти" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/");
  await page.getByRole("link", { name: "Условия" }).click();
  await expect(page).toHaveURL(/\/terms$/);
  await page.goto("/");
  await page.getByRole("link", { name: "Политика ПДн" }).click();
  await expect(page).toHaveURL(/\/privacy$/);
});
