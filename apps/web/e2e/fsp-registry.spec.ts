import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD } from "./fixtures";

/**
 * ФСП — реестр + заявка. Стенд после `make seed` (или `make demo-reset`): жюри-кандидат есть в реестре с email
 * аккаунта и не привязан. (1) «Привязать ФСП» → «найден в базе» → достижения на Главной и в профиле.
 * (2) Новый кандидат с чужим email → заявка → в очереди админа → принята → привязано.
 */

const JURY = "jury-candidate@demo.fsp.test";
const ADMIN = "admin@demo.fsp.test";

async function login(page: Page, email: string, password = DEMO_PASSWORD) {
  await page.goto("/login");
  await page.locator('input[type="email"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 });
}

test.describe.configure({ mode: "serial" });

test("жюри-кандидат привязывает ФСП одной кнопкой", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, JURY);
  await page.goto("/me/profile?tab=data");
  const panel = page.getByTestId("profile-fsp");
  await panel.getByRole("button", { name: "Привязать ФСП" }).click();
  await expect(panel.getByText("Ваш email найден в базе ФСП")).toBeVisible();
  await expect(panel.getByText("ФСП подтверждена")).toBeVisible({ timeout: 30_000 });
  // достижения импортируются асинхронно (fsp.linked → fsp.sync → fsp.results.imported)
  await expect(panel.getByText("Достижения и подтверждения обновлены")).toBeVisible({ timeout: 30_000 });
  await page.goto("/me");
  await expect(page.getByTestId("home-fsp")).toContainText("Кубок по продуктовому программированию");
});

test("заявка с чужим email → админ принимает → привязано", async ({ browser }) => {
  const cand = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const email = `e39-28-${Date.now()}@e2e.fsp.test`;
  await cand.goto("/register");
  await cand.getByTestId("auth-email").fill(email);
  await cand.getByTestId("auth-password").fill("e2e-pass-12345");
  await cand.getByTestId("auth-consent-pd").click();
  await cand.getByTestId("auth-submit").click();
  await expect(cand).not.toHaveURL(/\/register/);

  await cand.goto("/me/profile?tab=data");
  const panel = cand.getByTestId("profile-fsp");
  await panel.getByRole("button", { name: "Привязать ФСП" }).click();
  await expect(panel.getByText(/Ваших контактов нет в базе ФСП/)).toBeVisible();
  await panel.getByLabel("ФИО, как в протоколах ФСП").fill("Дроздова Алина Петровна");
  await panel.getByLabel("Email, под которым вы участвовали").fill("alina.drozdova@example.test");
  await panel.getByLabel("Мероприятие ФСП").fill("Региональные соревнования по алгоритмическому программированию");
  await panel.getByRole("button", { name: "Отправить заявку" }).click();
  await expect(panel.getByTestId("fsp-request-pending")).toBeVisible();

  const admin = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await login(admin, ADMIN);
  await admin.goto("/federation");
  // «Что требует вас» на главной админки ведёт в очередь заявок
  await admin.getByTestId("queue-fsp_requests").click();
  await expect(admin).toHaveURL(/\/federation\/requests/);
  const card = admin.getByTestId("fsp-request").filter({ hasText: "Дроздова Алина Петровна" }).first();
  await expect(card).toBeVisible();
  // подсказка по совпавшему email уже выбрана
  await card.getByRole("button", { name: "Принять" }).click();
  await expect(admin.getByTestId("fsp-request").filter({ hasText: "Дроздова Алина Петровна" })).toHaveCount(0);

  await cand.reload();
  await expect(cand.getByTestId("profile-fsp").getByText("ФСП подтверждена")).toBeVisible({ timeout: 30_000 });
});
