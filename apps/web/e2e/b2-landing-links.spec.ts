import { expect, test } from "@playwright/test";

/** E39-34: кнопки лендинга ведут туда, что на них написано, и не на Главную без входа. */

test("b2: «Пройти тест» открывает регистрацию кандидата", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Пройти тест" }).click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.locator("#role-candidate")).toBeChecked();
});

test("b2: «Ищу сотрудников» открывает регистрацию компании", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Ищу сотрудников" }).click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.locator("#role-employer")).toBeChecked();
});

test("b2: «Войти» и подвал ведут на свои экраны", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Войти" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/");
  await page.getByRole("link", { name: "Документы" }).click();
  await expect(page).toHaveURL(/\/terms$/);
  await page.goto("/");
  await page.getByRole("link", { name: "Политика ПДн" }).click();
  await expect(page).toHaveURL(/\/privacy$/);
});
