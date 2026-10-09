import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { test, type Page } from "@playwright/test";

import { DEMO_PASSWORD, HEROES } from "./fixtures";

/**
 * E39-36: прогон всех путей глазами жюри после E39. Под каждой ролью (кандидат, работодатель, админ/ФСП и публичные
 * страницы) открывает экраны в светлой и тёмной теме на 1440 и 375, делает снимки и собирает находки: ошибки консоли,
 * 5xx, горизонтальную прокрутку, «undefined/NaN», нативные select и number-поля, пустые страницы, белые блоки в тёмной теме.
 *
 * Стенд с сидом: `make up-lite && make seed`. Запуск: `E2E_CHANNEL=chrome pnpm e2e e2e/joint-e39-check.spec.ts --project=desktop`.
 * Снимки — в `E39_CHECK_OUT` (по умолчанию `../../reports/e39-check/shots`), находки — `findings.json` рядом.
 */
const OUT = process.env.E39_CHECK_OUT ?? "../../reports/e39-check/shots";
const ROLES = {
  candidate: HEROES.anya.email,
  employer: HEROES.olga.email,
  admin: "admin@demo.fsp.test",
} as const;
type Role = keyof typeof ROLES | "public";

const STATIC: Record<Role, string[]> = {
  public: ["/", "/login", "/register", "/jobs", "/terms", "/privacy"],
  candidate: [
    "/me", "/me/profile", "/me/profile?tab=skills", "/me/profile?tab=data", "/me/profile?tab=graph", "/me/stats",
    "/me/offers", "/me/offers?show=interests", "/me/navigator", "/me/assessment", "/me/assessment/history", "/me/tasks",
    "/settings", "/jobs",
  ],
  employer: [
    "/employer", "/employer/search", "/employer/vacancies", "/employer/shortlist", "/employer/offers", "/employer/company",
    "/employer/tasks", "/employer/families/guide", "/employer/families/new", "/employer/subscriptions", "/settings",
  ],
  admin: [
    "/federation", "/federation/requests", "/federation/moderation", "/federation/registry", "/federation/funnel",
    "/admin/families", "/admin/professions", "/admin/skills", "/admin/quality", "/admin/quality/fairness",
    "/admin/quality/runs", "/admin/demo/two-worlds", "/admin/demo/llm-exam", "/admin/demo/new-profession", "/settings",
  ],
};
/** Страницы с id: находим первую ссылку такого вида на уже открытых страницах. */
const DISCOVER: Record<Role, { from: string; re: RegExp }[]> = {
  public: [{ from: "/jobs", re: /^\/jobs\/[^/?]+$/ }],
  candidate: [
    { from: "/jobs", re: /^\/jobs\/[^/?]+$/ },
    { from: "/me/offers", re: /^\/me\/offers\/[^/?]+$/ },
    { from: "/me/assessment/history", re: /^\/me\/assessment\/attempts\/[^/]+\/(result|review)$/ },
  ],
  employer: [
    { from: "/employer/search", re: /^\/employer\/candidates\/[^/?]+/ },
    { from: "/employer/vacancies", re: /^\/employer\/vacancies\/[^/]+$/ },
    { from: "/employer/vacancies", re: /^\/employer\/vacancies\/[^/]+\/shortlist$/ },
    { from: "/employer/offers", re: /^\/employer\/offers\/[^/?]+$/ },
  ],
  admin: [],
};

type Finding = { sev: "P1" | "P2" | "P3"; role: string; route: string; vp: string; theme: string; kind: string; detail: string };
const findings: Finding[] = [];
const shots: string[] = [];

async function login(page: Page, email: string) {
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto("/login");
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill(DEMO_PASSWORD);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(2500);
    if (!/\/login/.test(page.url())) return;
    await page.waitForTimeout(20_000);
  }
}

test.afterAll(() => {
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, "findings.json"), `${JSON.stringify({ findings, shots }, null, 2)}\n`, "utf8");
});

const VPS = [
  { name: "1440", width: 1440, height: 900 },
  { name: "375", width: 375, height: 812 },
] as const;

for (const role of ["public", "candidate", "employer", "admin"] as const) {
  for (const vp of VPS) {
    for (const theme of ["light", "dark"] as const) {
      test(`e39-check ${role} ${vp.name} ${theme}`, async ({ page }, info) => {
        test.skip(info.project.name !== "desktop", "размеры задаются в тесте");
        test.setTimeout(900_000);
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await page.addInitScript((t) => localStorage.setItem("fsp-theme", t), theme);
        if (role !== "public") await login(page, ROLES[role]);
        page.setDefaultTimeout(6_000);

        let route = "";
        const add = (sev: Finding["sev"], kind: string, detail: string) =>
          findings.push({ sev, role, route, vp: vp.name, theme, kind, detail: detail.slice(0, 300) });
        page.on("console", (m) => {
          if (m.type() === "error") add("P2", "console", m.text());
        });
        page.on("pageerror", (e) => add("P1", "pageerror", String(e)));
        page.on("response", (r) => {
          const u = r.url();
          if (r.status() >= 500 && u.includes("/api/")) add("P1", "http5xx", `${r.status()} ${u}`);
          else if (r.status() >= 400 && r.status() !== 401 && r.status() !== 429 && u.includes("/api/")) add("P3", "http4xx", `${r.status()} ${u}`);
        });

        const visit = async (path: string) => {
          route = path;
          await page.goto(path, { waitUntil: "domcontentloaded" });
          await page.waitForLoadState("networkidle", { timeout: 8_000 }).catch(() => undefined);
          await page.waitForTimeout(700);
          const probe = await page.evaluate(() => {
            const text = document.body.innerText;
            const root = document.documentElement;
            const whites = [...document.querySelectorAll<HTMLElement>("main *")].filter((el) => {
              const r = el.getBoundingClientRect();
              return r.width > 200 && r.height > 60 && getComputedStyle(el).backgroundColor === "rgb(255, 255, 255)";
            }).length;
            return {
              len: text.trim().length,
              hscroll: root.scrollWidth > root.clientWidth + 2,
              bad: /\bundefined\b|\bNaN\b|\[object|Не удалось|Ошибка загрузки/.exec(text)?.[0] ?? "",
              selects: document.querySelectorAll("select").length,
              numbers: document.querySelectorAll('input[type="number"]').length,
              whites,
              url: location.pathname + location.search,
            };
          });
          if (probe.len < 40) add("P1", "empty", `текста ${probe.len}`);
          if (probe.hscroll) add("P2", "hscroll", "горизонтальная прокрутка");
          if (probe.bad) add("P2", "bad-text", probe.bad);
          if (probe.selects) add("P2", "native-select", String(probe.selects));
          if (probe.numbers) add("P2", "native-number", String(probe.numbers));
          if (theme === "dark" && probe.whites) add("P2", "white-block", `${probe.whites} белых блоков`);
          if (probe.url.split("?")[0] !== path.split("?")[0]) add("P3", "redirect", `${path} → ${probe.url}`);
          const name = `${role}${path.replace(/[/?=&]+/g, "_")}_${vp.name}_${theme}.png`;
          await page.screenshot({ path: join(OUT, name), fullPage: true });
          shots.push(name);
        };

        mkdirSync(OUT, { recursive: true });
        for (const p of STATIC[role]) await visit(p).catch((e) => add("P1", "visit", String(e)));
        for (const d of DISCOVER[role]) {
          route = d.from;
          try {
            await page.goto(d.from, { waitUntil: "domcontentloaded" });
            await page.waitForLoadState("networkidle", { timeout: 8_000 }).catch(() => undefined);
            const hrefs = await page.$$eval("a", (as) => as.map((a) => a.getAttribute("href") ?? ""));
            const hit = hrefs.find((h) => d.re.test(h));
            if (hit) await visit(hit);
            else add("P3", "no-link", `на ${d.from} нет ссылки ${d.re}`);
          } catch (e) {
            add("P1", "discover", String(e));
          }
        }
      });
    }
  }
}
