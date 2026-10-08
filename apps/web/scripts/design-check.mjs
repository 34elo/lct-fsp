#!/usr/bin/env node
// E38-16: снимки экранов приложения для сверки с макетами v2 (docs/design/v2/png).
//   node scripts/design-check.mjs [--base http://localhost:28080] [--out ../../reports/design-check]
// Нужен стенд с сидом (make up-lite && make seed). Браузер: Chromium Playwright или SHOT_CHANNEL=msedge|chrome.
// Результат: <out>/app/<экран>_<ширина>.png и manifest.json (экран → макет); пары собирает pair.py.
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

import { chromium } from "@playwright/test";

const arg = (k, d) => {
  const i = process.argv.indexOf(k);
  return i > 0 ? process.argv[i + 1] : d;
};
const BASE = arg("--base", "http://localhost:28080");
const OUT = resolve(arg("--out", "../../reports/design-check"));
const PASS = process.env.E2E_DEMO_PASSWORD ?? "demo-pass-1234";
const WIDTHS = [1440, 375];
mkdirSync(join(OUT, "app"), { recursive: true });

const browser = await chromium
  .launch(process.env.SHOT_CHANNEL ? { channel: process.env.SHOT_CHANNEL } : {})
  .catch(() => chromium.launch({ channel: "msedge" }));
const manifest = [];

async function session(email, width) {
  const ctx = await browser.newContext({ viewport: { width, height: width > 700 ? 900 : 812 } });
  const page = await ctx.newPage();
  if (email) {
    await page.goto(`${BASE}/login`);
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(PASS);
    await page.keyboard.press("Enter");
    await page.waitForURL((u) => !/\/login/.test(u.pathname));
    if (/consents/.test(page.url())) {
      await page.locator('button[role="checkbox"]').first().click(); // обязательное согласие (ПДн)
      await page.waitForTimeout(300);
      await page.locator('button[type="submit"]').click();
      await page.waitForURL((u) => !/consents/.test(u.pathname));
    }
  }
  return page;
}

async function shot(page, name, mock, path, width, { wait = 2500, prep, stay } = {}) {
  try {
    if (!stay) await page.goto(`${BASE}${path}`);
    await page.waitForTimeout(wait);
    if (prep) await prep(page);
    await page.screenshot({ path: join(OUT, "app", `${name}_${width}.png`), fullPage: true });
    manifest.push({ name, mock: `${mock}_${width}`, path, width, url: page.url() });
    console.log("ok", name, width, page.url().replace(BASE, ""));
  } catch (e) {
    console.log("FAIL", name, width, String(e).slice(0, 120));
  }
}

const links = (page, re) => page.$$eval("a", (as, s) => [...new Set(as.map((a) => a.getAttribute("href")).filter((h) => h && new RegExp(s).test(h)))], re.source);

for (const w of WIDTHS) {
  let p = await session(null, w);
  await shot(p, "landing", "v2_landing__main", "/", w);

  p = await session("anya@demo.fsp.test", w);
  await shot(p, "me", "v2_me__after", "/me", w);
  await shot(p, "me-stats", "v2_me-stats__main", "/me/stats", w);
  await shot(p, "me-assessment", "v2_me-assessment__main", "/me/assessment", w);
  await p.goto(`${BASE}/me/assessment/history`);
  await p.waitForTimeout(2000);
  const res = await links(p, /attempts\/.*\/result/);
  if (res[0]) await shot(p, "me-result", "v2_me-assessment-result__confirmed", res[0], w);
  if (res[1]) await shot(p, "me-result2", "v2_me-assessment-result__not-confirmed", res[1], w);
  await shot(p, "me-profile", "v2_me-profile__main", "/me/profile", w);
  await shot(p, "me-settings", "v2_me-settings__main", "/me/settings", w);
  await shot(p, "me-offers", "v2_me-offers__main", "/me/offers", w);

  p = await session("dima@demo.fsp.test", w);
  await shot(p, "me-dima", "v2_me__before", "/me", w);
  await shot(p, "me-assessment-dima", "v2_me-assessment__main", "/me/assessment", w);

  p = await session("olga@demo.fsp.test", w);
  await shot(p, "employer", "v2_employer__first", "/employer", w);
  await p.goto(`${BASE}/employer`);
  await p.waitForTimeout(1500);
  await p.locator("input, textarea").first().fill("Backend на Python, Middle, до 220 тыс., удалёнка");
  await p.getByRole("button", { name: "Подобрать" }).click();
  await p.waitForTimeout(6000);
  await p.waitForTimeout(10000);
  await shot(p, "employer-results", "v2_employer__results", p.url().replace(BASE, ""), w, { wait: 300, stay: true });
  const cands = await links(p, /employer\/candidates\//);
  console.log("candidates", cands.slice(0, 2));
  let cat = null;
  cat = (await links(p, /employer\/categories\//))[0] ?? null;
  console.log("category", cat);
  await shot(p, "employer-shortlist", "v2_employer-shortlist__main", "/employer/shortlist", w);
  await shot(p, "employer-offers", "v2_employer-offers__main", "/employer/offers", w);
  if (cat) {
    await shot(p, "employer-category", "v2_employer-categories__main", cat, w, { wait: 5000 });
  }
  if (cands[0]) await shot(p, "employer-candidate", "v2_employer-candidate__main", cands[0], w, { wait: 4000 });
}
writeFileSync(join(OUT, "manifest.json"), JSON.stringify(manifest, null, 1));
await browser.close();
