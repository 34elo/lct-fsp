import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { DEMO_PASSWORD } from "./fixtures";

/**
 * E39-30: автоаудит админки. Проходит все маршруты `/admin/*` и `/federation*` под `admin@` на 1440 и 375,
 * в светлой и тёмной теме, и собирает: ошибки консоли и сети, горизонтальную прокрутку, пустые и сломанные
 * состояния, двойной логотип, ссылки в никуда и кнопки без видимого эффекта.
 *
 * Стенд с сидом: `make up-lite && make seed`. Запуск: `pnpm e2e e2e/b2-admin-audit.spec.ts`.
 * Сырые находки пишутся в `ADMIN_AUDIT_OUT` (по умолчанию `../../reports/admin-audit.json`); отчёт — `reports/admin-audit.md`.
 * Тест падает только на P1 (белый экран, 5xx, ошибка рендера); остальное — в отчёте.
 */

const ADMIN = process.env.E2E_ADMIN_EMAIL ?? "admin@demo.fsp.test";
const OUT = process.env.ADMIN_AUDIT_OUT ?? "../../reports/admin-audit.json";

const ROUTES = [
  "/federation",
  "/federation/moderation",
  "/federation/registry",
  "/federation/funnel",
  "/admin/families",
  "/admin/professions",
  "/admin/skills",
  "/federation/analytics",
  "/admin/demo/two-worlds",
  "/admin/demo/llm-exam",
  "/admin/demo/new-profession",
];

const VIEWPORTS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "375", width: 375, height: 812 },
] as const;
const THEMES = ["light", "dark"] as const;

/** Кнопки, которые меняют данные: в аудите не нажимаем. */
const MUTATING = /принять|отклонить|удалить|скрыть|одобрить|допустить|заблокировать|отозвать|сохранить|создать|запустить|добавить|выйти|загрузить|импорт|применить|подтвердить|отправить|снять|архив/i;

type Finding = { sev: "P1" | "P2" | "P3"; route: string; vp: string; theme: string; kind: string; detail: string };
const findings: Finding[] = [];

async function login(page: Page) {
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(ADMIN);
    await page.locator('input[type="password"]').fill(DEMO_PASSWORD);
    await page.keyboard.press("Enter");
    const ok = await expect(page).not.toHaveURL(/\/login/, { timeout: 8_000 }).then(() => true, () => false);
    if (ok) return;
    await page.waitForTimeout(20_000);
  }
  await expect(page).not.toHaveURL(/\/login/);
}

test.afterAll(() => {
  mkdirSync(dirname(OUT), { recursive: true });
  writeFileSync(OUT, `${JSON.stringify(findings, null, 2)}\n`, "utf8");
});

for (const vp of VIEWPORTS) {
  for (const theme of THEMES) {
    test(`admin-audit ${vp.name} ${theme}`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name !== "desktop", "размеры задаются в самом тесте; второй проект дублировал бы прогон");
      test.setTimeout(600_000);
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.addInitScript((t) => localStorage.setItem("fsp-theme", t), theme);
      await login(page);
      page.setDefaultTimeout(5_000);

      let route = "";
      const add = (sev: Finding["sev"], kind: string, detail: string) =>
        findings.push({ sev, route, vp: vp.name, theme, kind, detail: detail.slice(0, 300) });

      page.on("console", (m) => {
        if (m.type() === "error" || m.type() === "warning") add(m.type() === "error" ? "P2" : "P3", `console.${m.type()}`, m.text());
      });
      page.on("pageerror", (e) => add("P1", "pageerror", e.message));
      page.on("requestfailed", (r) => {
        if (!/net::ERR_ABORTED/.test(r.failure()?.errorText ?? "")) add("P2", "requestfailed", `${r.method()} ${r.url()} ${r.failure()?.errorText}`);
      });
      page.on("response", (r) => {
        if (!r.url().includes("/api/") || r.status() < 400) return;
        add(r.status() >= 500 ? "P1" : "P2", `http.${r.status()}`, `${r.request().method()} ${new URL(r.url()).pathname}`);
      });

      const hrefs = new Set<string>();
      for (route of ROUTES) {
        await page.goto(route);
        await page.waitForLoadState("networkidle", { timeout: 4_000 }).catch(() => undefined);
        await page.waitForTimeout(500);

        if (new URL(page.url()).pathname !== route) add("P2", "redirect", `ушли на ${new URL(page.url()).pathname}`);
        const text = (await page.locator("body").innerText()).trim();
        if (text.length < 80) add("P1", "empty-page", `текста на странице ${text.length} символов`);
        for (const bad of [/undefined/, /\bNaN\b/, /\[object /, /\bnull\b/, /Something went wrong/i, /Не удалось/i, /Ошибка/i, /404/, /Cannot read/]) {
          const m = text.match(bad);
          if (m) add(bad.source === "Не удалось" || /Ошибка/.test(bad.source) ? "P2" : "P2", "bad-text", `«${m[0]}» в тексте страницы`);
        }
        if (await page.locator('[class*="skeleton" i], [aria-busy="true"]').count()) add("P3", "still-loading", "скелетоны/aria-busy после networkidle");

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        if (overflow > 1) add("P2", "h-overflow", `горизонтальная прокрутка ${overflow}px`);

        const logos = await page.locator('a[href="/"] img, [data-testid*="logo" i], img[alt*="логотип" i], img[alt*="logo" i]').evaluateAll((els) =>
          els.filter((e) => (e as HTMLElement).offsetParent !== null || getComputedStyle(e).position === "fixed").length,
        );
        if (logos > 1) add("P3", "logo-twice", `видимых логотипов: ${logos}`);

        const h1 = await page.locator("h1").count();
        if (h1 !== 1) add("P3", "h1", `заголовков h1: ${h1}`);

        const bad = await page.evaluate(() => {
          const out: string[] = [];
          for (const el of Array.from(document.querySelectorAll("button, a, [role=button]"))) {
            const e = el as HTMLElement;
            const name = (e.innerText || e.getAttribute("aria-label") || e.getAttribute("title") || "").trim();
            if (!name && !e.querySelector("img,svg[aria-label]")) out.push(`${el.tagName.toLowerCase()} без имени`);
            if (el.tagName === "A") {
              const h = el.getAttribute("href");
              if (!h || h === "#" || h.startsWith("javascript:")) out.push(`ссылка «${name}» с href=${h}`);
            }
          }
          return out;
        });
        for (const b of bad) add("P2", "a11y/dead-link", b);

        // тёмная тема: контраст не считаем, но ловим белые блоки на тёмном фоне
        if (theme === "dark") {
          const whites = await page.evaluate(() => {
            let n = 0;
            for (const el of Array.from(document.querySelectorAll("main *, body > div *"))) {
              const r = (el as HTMLElement).getBoundingClientRect();
              if (r.width < 120 || r.height < 24) continue;
              const bg = getComputedStyle(el).backgroundColor;
              const m = bg.match(/rgba?\((\d+), (\d+), (\d+)(?:, ([\d.]+))?\)/);
              if (m && +m[1] > 245 && +m[2] > 245 && +m[3] > 245 && (m[4] === undefined || +m[4] > 0.9)) n++;
            }
            return n;
          });
          if (whites) add("P3", "dark-white-block", `белых блоков в тёмной теме: ${whites}`);
        }

        for (const h of await page.locator("a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""))) {
          if (h.startsWith("/") && !h.startsWith("//")) hrefs.add(h);
        }

        // кнопки: нажимаем безопасные и смотрим, что изменилось (URL, DOM, запрос, диалог)
        const buttons = page.locator("main button:visible, [role=main] button:visible, [role=tab]:visible");
        const n = Math.min(await buttons.count(), 12);
        for (let i = 0; i < n; i++) {
          const b = buttons.nth(i);
          const label = ((await b.innerText().catch(() => "")) || (await b.getAttribute("aria-label").catch(() => "")) || "").trim();
          if (MUTATING.test(label) || (await b.isDisabled().catch(() => true))) continue;
          // уже выбранная вкладка/фильтр: повторное нажатие эффекта не даёт
          if ((await b.getAttribute("aria-selected").catch(() => null)) === "true" || (await b.getAttribute("aria-pressed").catch(() => null)) === "true" || (await b.getAttribute("aria-current").catch(() => null))) continue;
          const before = await page.evaluate(() => document.body.innerHTML.length + "|" + location.href);
          let requests = 0;
          const onReq = () => requests++;
          page.on("request", onReq);
          await b.click({ timeout: 3_000 }).catch(() => undefined);
          await page.waitForTimeout(400);
          page.off("request", onReq);
          const after = await page.evaluate(() => document.body.innerHTML.length + "|" + location.href);
          const dialog = await page.locator('[role=dialog]').count();
          if (before === after && !requests && !dialog) add("P3", "dead-button", `«${label || "?"}» не даёт видимого эффекта`);
          if (new URL(page.url()).pathname !== route) await page.goto(route);
          else if (dialog) await page.keyboard.press("Escape");
        }
      }

      // внутренние ссылки со страниц админки ведут на существующие экраны
      route = "(links)";
      for (const h of [...hrefs].sort()) {
        const r = await page.goto(h);
        await page.waitForTimeout(300);
        const t = await page.locator("body").innerText();
        if ((r && r.status() >= 400) || /404|не найден|страница не существует/i.test(t.slice(0, 400))) add("P2", "broken-link", `${h} → не найден`);
      }

      await page.screenshot({ path: `test-results/admin-audit-${vp.name}-${theme}.png` }).catch(() => undefined);
      const p1 = findings.filter((f) => f.sev === "P1" && f.vp === vp.name && f.theme === theme);
      expect(p1, JSON.stringify(p1, null, 1)).toEqual([]);
    });
  }
}
