import { expect, test, type Page } from "@playwright/test";

/**
 * Выдача пароля HR. Владелец создаёт доступ — логин и временный пароль показаны в модалке; HR входит
 * временным паролем, задаёт свой и попадает в кабинет; повторный вход новым паролем работает, временным — нет.
 * Нужен поднятый стек (`make up`), запуск: `pnpm exec playwright test e2e/hr-password.spec.ts`.
 */

const PASS = "e2e-pass-12345";
const NEW_PASS = "e2e-new-pass-678";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill(password);
  await page.getByTestId("auth-submit").click();
}

test("HR входит временным паролем, меняет его и входит новым", async ({ page, browser }) => {
  const stamp = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const owner = `e43-3-owner-${stamp}@e2e.fsp.test`;
  const hr = `e43-3-hr-${stamp}@e2e.fsp.test`;

  // Владелец: регистрация, компания, вкладка «Команда».
  await page.goto("/register");
  await page.getByTestId("auth-role-employer").click();
  await page.getByTestId("auth-email").fill(owner);
  await page.getByTestId("auth-password").fill(PASS);
  await page.getByTestId("auth-consent-pd").click();
  await page.getByTestId("auth-submit").click();
  await expect(page).toHaveURL(/\/employer$/);
  await page.getByTestId("onboarding-company-name").fill("Парольная Компания");
  await page.getByTestId("onboarding-company-submit").click();
  await page.goto("/employer/company?tab=team");

  // Выдача доступа: пароль показан в модалке, не в alert/confirm.
  page.on("dialog", (d) => {
    throw new Error(`нативный диалог: ${d.message()}`);
  });
  await page.getByTestId("company-hr-name").fill("Анна Смирнова");
  await page.getByTestId("company-hr-email").fill(hr);
  await page.getByTestId("company-hr-submit").click();
  const modal = page.getByRole("alertdialog");
  await expect(modal).toBeVisible();
  await expect(page.getByTestId("company-access-once")).toContainText("один раз");
  const temp = (await page.getByTestId("company-access-password").innerText()).trim();
  expect(temp).toMatch(/^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$/);
  await page.getByTestId("company-access-close").click();
  await expect(modal).toBeHidden();

  // HR в чистом контексте: временный пароль → форма смены → кабинет.
  const ctx = await browser.newContext();
  const hrPage = await ctx.newPage();
  await login(hrPage, hr, temp);
  await expect(hrPage).toHaveURL(/\/password\/new/);
  await hrPage.getByTestId("password-setup-new").fill(NEW_PASS);
  await hrPage.getByTestId("password-setup-repeat").fill(NEW_PASS);
  await hrPage.getByTestId("password-setup-submit").click();
  await expect(hrPage).not.toHaveURL(/\/(password\/new|login)/);

  // Выход и повторный вход: новым — да, временным — нет.
  await hrPage.context().clearCookies();
  await login(hrPage, hr, temp);
  await expect(hrPage.getByText("Неверная почта или пароль")).toBeVisible();
  await login(hrPage, hr, NEW_PASS);
  await expect(hrPage).not.toHaveURL(/\/(password\/new|login)/);
  await ctx.close();
});
