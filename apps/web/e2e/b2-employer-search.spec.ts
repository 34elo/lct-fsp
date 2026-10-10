import { expect, test } from "@playwright/test";

import { loginAs } from "./fixtures";

/**
 * E39-21: поиск сотрудников на «Подборе». Фраза «python django middle» → чипсы навыков и грейд в условиях →
 * категории с объяснением «почему» → компактные карточки кандидатов; состояние в URL; фильтр сужает выдачу.
 */
test("b2: запрос «python django middle» → чипсы → категории → кандидаты; фильтры сужают выдачу", async ({ page }) => {
  await loginAs(page, "olga");
  await page.goto("/employer");

  const query = page.getByRole("combobox", { name: "Кого вы ищете" });
  await query.fill("python django middle");
  await page.getByRole("option", { name: /Разобрать «python django middle»/ }).click();

  // Чипсы: навыки — в строке, грейд — в условиях.
  await expect(page.getByTestId("query-chip-skill").filter({ hasText: "Python" })).toBeVisible();
  await expect(page.getByTestId("query-chip-skill").filter({ hasText: "Django" })).toBeVisible();
  await expect(page.getByTestId("filter-grade-middle")).toHaveAttribute("aria-pressed", "true"); // грейд — в панели

  // По умолчанию «Кандидаты»; категории с объяснением — переключателем; условия — в ссылке.
  await expect(page.getByTestId("match-candidates")).toBeVisible();
  await page.getByRole("radio", { name: "Категории" }).click();
  const cats = page.getByTestId("match-categories");
  await expect(cats.getByRole("button", { pressed: true })).toBeVisible();
  await expect(page.getByTestId("match-why")).toContainText("Python");
  await expect(page).toHaveURL(/skill=python.*grade=middle.*need=.*view=categories|skill=python.*grade=middle.*view=categories.*need=/);
  const cards = page.getByTestId("match-top").getByRole("article");
  await expect(cards.first()).toBeVisible();
  const before = await cards.count();

  // Ссылка воспроизводит выдачу.
  await page.reload();
  await expect(page.getByTestId("query-chip-skill").filter({ hasText: "Python" })).toBeVisible();
  await expect(page.getByTestId("match-top").getByRole("article").first()).toBeVisible();

  // Фильтр сужает выдачу: «только подтверждённый грейд» + доверие ●●●● + ожидания до 50 000.
  await page.goto(`${new URL(page.url()).pathname}?skill=python&skill=django&grade=middle&confirmed=1&trust=4&to=50000`);
  await expect(page.getByTestId("filter-confirmed")).toBeChecked(); // заданное — подсвечено в панели
  await expect(page).toHaveURL(/need=/);
  await expect(cats.or(page.getByText("Под запрос нет категорий"))).toBeVisible();
  const top = page.getByTestId("match-top");
  await expect(top.or(page.getByText("В категории под эти фильтры никого нет")).or(page.getByText("Под запрос нет категорий"))).toBeVisible();
  const after = await top.getByRole("article").count();
  expect(after).toBeLessThanOrEqual(before);
});

/** E41-11: переключатель «Категории / Кандидаты», фильтры свёрнуты, «В шорт-лист» на карточке. */
test("b2: режим «Кандидаты» → фильтр навыка → «В шорт-лист»", async ({ page }) => {
  await loginAs(page, "olga");
  await page.goto("/employer?skill=python&grade=middle&view=categories");
  await expect(page.getByTestId("match-categories")).toBeVisible();
  await expect(page.getByTestId("filter-fsp")).toHaveCount(0); // блоки фильтров закрыты

  await page.getByRole("radio", { name: "Кандидаты" }).click();
  await expect(page).not.toHaveURL(/view=/); // «Кандидаты» — вид по умолчанию
  const list = page.getByTestId("match-candidates");
  const first = list.getByRole("article").first();
  await expect(first).toBeVisible();

  await expect(page.getByTestId("filter-skills")).toBeVisible(); // заполненный блок раскрыт

  await first.getByRole("button", { name: "В шорт-лист" }).click();
  await expect(first.getByRole("button", { name: "В шорт-листе" })).toBeVisible();
});
