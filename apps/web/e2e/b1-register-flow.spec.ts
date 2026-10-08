import { expect, test, type Page } from "@playwright/test";

/**
 * E39-6: регистрация → тест одним потоком. Новый кандидат отмечает только обязательное согласие
 * в форме регистрации и сразу попадает в «Шаг 1. Направление и навыки → Шаг 2. Грейд и ожидания →
 * Шаг 3. Тест», без Главной и экрана согласий. В UI нет слова «опрос»; все профессии справочника
 * выбираются (тонкий банк помечен «бета»).
 */

/** Крупная карточка выбора (направление или грейд): кликаем по ней, как человек. */
const card = (page: Page, value: string) => page.locator(`label[data-choice="${value}"]`);

/** «опрос» отдельным словом (не «вопрос»). */
const SURVEY_WORD = /(^|[^а-яё])опрос/i;

async function noSurveyWord(page: Page) {
  const text = await page.locator("body").innerText();
  expect(text, "в UI не должно быть слова «опрос»").not.toMatch(SURVEY_WORD);
}

test("b1: регистрация → первый вопрос теста без лишних кликов", async ({ page, request }) => {
  const email = `e39-6-${Date.now()}-${Math.floor(Math.random() * 1e6)}@e2e.fsp.test`;

  await page.goto("/register");
  await page.getByTestId("auth-email").fill(email);
  await page.getByTestId("auth-password").fill("e2e-pass-12345");
  await page.getByTestId("auth-consent-pd").click();
  await noSurveyWord(page);
  await page.getByTestId("auth-submit").click();

  // Шаг 1 — сразу после регистрации, без Главной и экрана согласий.
  await expect(page).toHaveURL(/\/me\/assessment$/);
  await expect(page.getByTestId("flow-step-1")).toHaveAttribute("aria-current", "step");
  await expect(page.getByRole("heading", { name: "Направление и навыки" })).toBeVisible();
  await noSurveyWord(page);

  // Все профессии справочника выбираются.
  const profs = (await (await request.get("/api/v1/taxonomy/professions")).json()).professions as { slug: string; beta?: boolean }[];
  expect(profs.length).toBeGreaterThanOrEqual(7);
  for (const p of profs) {
    await card(page, p.slug).click();
    await expect(page.getByTestId(`assessment-profession-${p.slug}`)).toBeChecked();
    if (p.beta) await expect(page.getByTestId(`assessment-beta-${p.slug}`)).toBeVisible();
  }

  await card(page, "backend").click();
  await page.getByTestId("assessment-next").click();

  // Шаг 2 — грейд и ожидания.
  await expect(page.getByTestId("flow-step-2")).toHaveAttribute("aria-current", "step");
  await card(page, "junior").click();
  await expect(page.getByTestId("assessment-grade-junior")).toBeChecked();
  await noSurveyWord(page);
  await page.getByTestId("assessment-start").click();

  // Шаг 3 — первое задание теста.
  await expect(page).toHaveURL(/\/me\/assessment\/attempts\/[0-9a-f-]+$/);
  await expect(page.getByTestId("assessment-item")).toBeVisible({ timeout: 15_000 });
});
