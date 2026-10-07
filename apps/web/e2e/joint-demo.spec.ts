/**
 * Сквозной демо-сценарий в порядке ТЗ (AU-5, audit E-1), одним тестом по шагам:
 *   1. регистрация нового соискателя → согласия;
 *   2. опрос (сразу после согласий, E35-2a) и экспресс-тест → результат (категория/грейд) → Главная;
 *   3. работодатель (Ольга) описывает потребность и находит категорию с кандидатами;
 *   4. приглашение (оффер с вилкой) выбранному кандидату;
 *   5. отклик кандидата (Аня) на вакансию Ольги и отклик в кабинете работодателя.
 *
 * Ограничение: тест нельзя пройти «правильно» из UI (ответы скрыты), поэтому новый соискатель отвечает
 * «Не знаю» и грейд у него, как правило, не подтверждается. Поэтому шаги 3–5 идут по сид-кандидатам
 * (категории из `make seed`), а не по только что созданному аккаунту.
 *
 * Скриншоты: 1440 px (проект desktop) и 375 px (mobile-375) — в `test-results/` (в git не попадают)
 * и в приложениях отчёта. Запуск на поднятом стеке с сидом: `pnpm e2e e2e/joint-demo.spec.ts`.
 */
import { expect, test, type Browser, type Page, type TestInfo } from "@playwright/test";
import { loginAs } from "./fixtures";

const NEED_TEXT = "бэкенд на Python, высоконагруженный API, удалёнка, до 220 000 ₽";
const VACANCY_TITLE = "Backend-разработчик (Python) в команду API"; // tools/seed/heroes/olga.yaml
const NEW_USER_PASSWORD = "e2e-pass-1234";

test.setTimeout(240_000);

async function shot(page: Page, info: TestInfo, n: number, name: string): Promise<void> {
  const file = info.outputPath(`${String(n).padStart(2, "0")}-${name}-${info.project.name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await info.attach(`${String(n).padStart(2, "0")}-${name}`, { path: file, contentType: "image/png" });
}

/** Новый контекст (отдельная сессия) с тем же размером окна, что у основной страницы. */
async function freshPage(browser: Browser, baseURL: string | undefined, like: Page): Promise<Page> {
  const ctx = await browser.newContext({ baseURL, viewport: like.viewportSize() ?? undefined });
  return ctx.newPage();
}

test("joint: регистрация → опрос и тест → категория → работодатель находит → приглашение → отклик", async ({ page, browser, baseURL }, info) => {
  if (info.project.name === "desktop") await page.setViewportSize({ width: 1440, height: 900 });
  let n = 0;

  // --- 1. регистрация и согласия ---------------------------------------------------------------
  await test.step("регистрация соискателя", async () => {
    const email = `e2e-${Date.now()}-${info.project.name}@example.com`;
    await page.goto("/register");
    await page.getByTestId("auth-role-candidate").click();
    await page.getByTestId("auth-email").fill(email);
    await page.getByTestId("auth-password").fill(NEW_USER_PASSWORD);
    await shot(page, info, ++n, "register");
    await page.getByTestId("auth-submit").click();
    await expect(page).toHaveURL(/\/consents/);
  });

  await test.step("согласия", async () => {
    await expect(page.getByTestId("consents-form")).toBeVisible();
    const boxes = page.getByTestId("consents-form").getByRole("checkbox");
    for (let i = 0; i < (await boxes.count()); i++) {
      if ((await boxes.nth(i).getAttribute("aria-checked")) !== "true") await boxes.nth(i).click();
    }
    await shot(page, info, ++n, "consents");
    await page.getByTestId("consents-submit").click();
    await expect(page).not.toHaveURL(/\/consents/);
  });

  // --- 2. опрос и экспресс-тест ----------------------------------------------------------------
  // Главный путь (E35-2a): после согласий новый кандидат сразу попадает в опрос.
  await test.step("опрос", async () => {
    // Если включено подтверждение email, дальше нужен код из письма (Mailpit): вручную, не в этом тесте.
    test.skip(/\/verify-email/.test(page.url()), "включено подтверждение email: код приходит в Mailpit, сценарий требует ручного шага");
    await expect(page).toHaveURL(/\/me\/assessment$/);
    // Без резюме направление не выбрано: экран начинается с одной кнопки «выбрать направление».
    const pick = page.getByTestId("assessment-pick");
    await expect(page.getByTestId("assessment-survey").or(pick)).toBeVisible();
    if (await pick.isVisible()) await pick.click();
    await expect(page.getByTestId("assessment-survey")).toBeVisible();
    // Радио и переключатель экспресса — скрытые input с видимой меткой-родителем: кликаем по метке.
    await page.locator('label:has([data-testid^="assessment-profession-"])').first().click();
    await page.getByTestId("assessment-format-remote").click(); // кнопка с aria-pressed
    await page.locator('label:has([data-testid="assessment-grade-junior"])').click();
    await page.locator('label:has([data-testid="assessment-express-toggle"])').click();
    await shot(page, info, ++n, "survey");
    await page.getByTestId("assessment-start").click();
    await expect(page).toHaveURL(/\/me\/assessment\/attempts\/[^/]+$/);
  });

  await test.step("экспресс-тест: отвечаем «Не знаю» до результата", async () => {
    await expect(page.getByTestId("assessment-item")).toBeVisible();
    await shot(page, info, ++n, "test-item");
    for (let i = 0; i < 40 && !/\/result/.test(page.url()); i++) {
      await page.getByTestId("assessment-skip").click({ timeout: 15_000 }).catch(() => undefined);
      await page.waitForTimeout(250);
    }
    await expect(page).toHaveURL(/\/result$/, { timeout: 30_000 });
    await expect(page.getByTestId("assessment-grade")).toBeVisible();
    await expect(page.getByTestId("assessment-express")).toBeVisible();
    await shot(page, info, ++n, "result");
  });

  await test.step("результат → Главная без баннера «пройдите тест»", async () => {
    await page.getByTestId("assessment-to-profile").click();
    await expect(page).toHaveURL(/\/me$/);
    await expect(page.getByTestId("path-banner")).toHaveCount(0);
    // Главная v2 (E38-1): после теста — следующий шаг и плитки «Сила», «Место», «Интересы».
    await expect(page.getByTestId("home-after")).toBeVisible();
    await expect(page.getByTestId("home-next-action")).toBeVisible();
    await shot(page, info, ++n, "home");
  });

  // --- 3. работодатель находит категорию и кандидата -------------------------------------------
  const olga = await freshPage(browser, baseURL, page);
  await test.step("работодатель: потребность → категории", async () => {
    await loginAs(olga, "olga");
    await olga.goto("/employer/needs/new");
    await olga.getByLabel("Кого ищете").fill(NEED_TEXT);
    await olga.getByRole("button", { name: "Показать категории" }).click();
    await expect(olga.getByRole("heading", { name: "Рекомендованные категории" })).toBeVisible();
    const open = olga.getByRole("link", { name: /Смотреть кандидатов/ }).first();
    await expect(open).toBeVisible({ timeout: 20_000 });
    await shot(olga, info, ++n, "employer-categories");
    await open.click();
    await expect(olga).toHaveURL(/\/employer\/categories\//);
    await expect(olga.getByRole("list", { name: "Кандидаты категории" })).toBeVisible({ timeout: 20_000 });
    await shot(olga, info, ++n, "employer-category-candidates");
  });

  // --- 4. приглашение (оффер с вилкой) ---------------------------------------------------------
  await test.step("работодатель: приглашение кандидату", async () => {
    const categoryUrl = olga.url();
    const invites = olga.getByRole("button", { name: "Интерес" });
    const total = Math.min(await invites.count(), 5);
    expect(total, "в категории нет кандидатов для приглашения").toBeGreaterThan(0);
    for (let i = 0; i < total; i++) {
      await invites.nth(i).click();
      await expect(olga.getByRole("heading", { name: /Оффер кандидату/ })).toBeVisible();
      // повторный прогон: кандидат мог получить оффер раньше, пробуем следующего
      if (await olga.getByText("Этому кандидату уже отправлялись офферы").isVisible()) {
        await olga.goto(categoryUrl);
        await expect(olga.getByRole("list", { name: "Кандидаты категории" })).toBeVisible();
        continue;
      }
      break;
    }
    const select = olga.locator("select").first();
    await expect.poll(() => select.locator("option").count(), { message: "нет опубликованных вакансий" }).toBeGreaterThan(1);
    await select.selectOption({ index: 1 });
    await expect(olga.locator('fieldset input[inputmode="numeric"]').first()).not.toHaveValue("");
    await olga.getByLabel("Сообщение кандидату").fill("Здравствуйте! Ваш профиль подходит под нашу вакансию: вилка указана сразу.");
    await shot(olga, info, ++n, "employer-offer-form");
    await olga.getByRole("button", { name: "Отправить оффер" }).click();
    await expect(olga).toHaveURL(/\/employer\/offers\/[^/]+$/, { timeout: 20_000 });
    await shot(olga, info, ++n, "employer-offer-sent");
  });

  // --- 5. отклик кандидата на вакансию ---------------------------------------------------------
  const anya = await freshPage(browser, baseURL, page);
  await test.step("кандидат: отклик на вакансию", async () => {
    await loginAs(anya, "anya");
    await anya.goto("/jobs");
    await expect(anya.getByRole("heading", { name: "Вакансии с открытой вилкой" })).toBeVisible();
    const card = anya.locator("article, li").filter({ hasText: VACANCY_TITLE }).first();
    await expect(card).toBeVisible({ timeout: 20_000 });
    await shot(anya, info, ++n, "jobs");
    await card.getByRole("link", { name: "Подробнее" }).click();
    await expect(anya).toHaveURL(/\/jobs\/[^/]+$/);
    await anya.getByLabel("Сообщение компании (по желанию)").fill("Интересна вакансия, готова к собеседованию.");
    await anya.getByRole("button", { name: "Откликнуться" }).click();
    // повторный прогон: сервер ответит «уже откликались» — отклик при этом на месте
    await expect(anya.getByText(/Отклик отправлен|Вы уже откликались/).first()).toBeVisible({ timeout: 20_000 });
    await shot(anya, info, ++n, "candidate-applied");
    await anya.goto("/me/responses");
    await expect(anya.getByRole("heading", { name: "Мои отклики" })).toBeVisible();
    await shot(anya, info, ++n, "candidate-responses");
  });

  await test.step("работодатель видит отклик", async () => {
    await olga.goto("/employer/responses");
    await expect(olga.getByRole("heading", { name: "Отклики на вакансии" })).toBeVisible();
    await expect(olga.getByText(VACANCY_TITLE).first()).toBeVisible({ timeout: 20_000 });
    await shot(olga, info, ++n, "employer-responses");
  });

  await olga.context().close();
  await anya.context().close();
});
