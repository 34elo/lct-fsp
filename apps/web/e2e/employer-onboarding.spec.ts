import { expect, test, type Page } from "@playwright/test";

/**
 * Новая компания. Регистрация работодателя → онбординг из трёх шагов (данные компании → первый запрос →
 * как устроен подбор) → первый подбор. В консоли нет ошибок, а ответов 4xx/5xx нет вовсе (кроме ожидаемого 401
 * тихого refresh у гостя до входа). Пропуск онбординга даёт пустые состояния с действием на всех экранах работодателя.
 */

function watch(page: Page) {
  const bad: string[] = [];
  const watching = { on: false };
  page.on("console", (m) => {
    if (watching.on && m.type() === "error") bad.push(`console: ${m.text()}`);
  });
  page.on("pageerror", (e) => bad.push(`pageerror: ${e.message}`));
  page.on("response", (r) => {
    if (watching.on && r.status() >= 400) bad.push(`${r.status()} ${r.url()}`);
  });
  return { bad, start: () => (watching.on = true) };
}

async function registerEmployer(page: Page) {
  const email = `e39-7-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.fsp.test`;
  await page.goto("/register");
  await page.getByTestId("auth-role-employer").click();
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill("e2e-pass-12345");
  await page.getByTestId("auth-consent-pd").click();
  await page.getByTestId("auth-submit").click();
  await expect(page).toHaveURL(/\/employer$/);
}

test("новый работодатель проходит онбординг и получает первый подбор без ошибок", async ({ page }) => {
  const w = watch(page);
  await registerEmployer(page);
  w.start();

  await expect(page.getByTestId("employer-onboarding")).toBeVisible();
  await expect(page.getByTestId("flow-step-1")).toHaveAttribute("aria-current", "step");

  // Шаг 1: компания.
  await page.getByTestId("onboarding-company-name").fill("Тестовая Компания");
  await page.getByTestId("onboarding-company-submit").click();

  // Шаг 2: первый запрос.
  await expect(page.getByTestId("flow-step-2")).toHaveAttribute("aria-current", "step");
  await page.getByRole("textbox", { name: "Кого вы ищете" }).fill("Backend на Python, Middle, до 220 тыс., удалёнка");
  await page.getByRole("button", { name: "Подобрать" }).click();

  // Шаг 3: как устроен подбор.
  await expect(page.getByTestId("flow-step-3")).toHaveAttribute("aria-current", "step");
  for (const k of ["category", "interest", "invitation"]) await expect(page.getByTestId(`onboarding-card-${k}`)).toBeVisible();
  await page.getByTestId("onboarding-done").click();

  // Первый подбор: категории запроса, лента и подписки с пустым состоянием и действием.
  await expect(page).toHaveURL(/\/employer\?.*need=/);
  await expect(page.getByTestId("match-candidates").or(page.getByTestId("match-categories"))).toBeVisible();
  await expect(page.getByTestId("match-feed-empty")).toBeVisible();
  await expect(page.getByTestId("match-subscriptions-empty").getByRole("link", { name: "Подписаться на категорию" })).toBeVisible();
  expect(w.bad).toEqual([]);
});

test("пропуск онбординга — пустые состояния с действием, на экранах работодателя нет 4xx и ошибок консоли", async ({ page }) => {
  const w = watch(page);
  await registerEmployer(page);
  w.start();

  await page.getByTestId("onboarding-skip").click();
  await expect(page.getByText("Сначала расскажите о компании")).toBeVisible();
  await expect(page.getByTestId("match-feed-empty")).toBeVisible();

  for (const path of ["/employer/vacancies", "/employer/shortlist", "/employer/responses", "/employer/tasks", "/employer/company", "/employer/subscriptions"]) {
    await page.goto(path);
    await expect(page.locator("h1").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
  }
  expect(w.bad).toEqual([]);

  // Онбординг не навязывается снова, но запускается кнопкой.
  await page.goto("/employer");
  await page.getByTestId("match-setup").click();
  await expect(page.getByTestId("employer-onboarding")).toBeVisible();
});
