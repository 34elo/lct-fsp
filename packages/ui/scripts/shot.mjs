#!/usr/bin/env node
// Скриншоты экрана для сверки с эталоном (backlog §E19, правило 5).
//   pnpm shot <маршрут> [--as candidate|employer|admin] [--playground] [--base URL] [--name ИМЯ]
// Ширины 1440, 1024, 390 × светлая и тёмная тема → reports/shots/<имя>-<ширина>-<тема>.png (6 файлов).
// Приложение ждём на http://localhost:28173 (`pnpm --filter fsp-web dev`), playground — на :28174
// (`pnpm --filter @fsp/ui dev`). Вход — через форму /login демо-аккаунтом из tools/seed/config.yaml.
// Браузер: Chromium Playwright; если он не установлен — системный Edge или Chrome (SHOT_CHANNEL=msedge|chrome).
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const WIDTHS = [1440, 1024, 390];
const THEMES = ["light", "dark"];
const ROLES = { candidate: "candidate_email", employer: "employer_email", admin: "admin_email" };

function parseArgs(argv) {
  const out = { route: "/", as: null, playground: false, base: null, name: null };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--as") out.as = argv[++i];
    else if (a === "--base") out.base = argv[++i];
    else if (a === "--name") out.name = argv[++i];
    else if (a === "--playground") out.playground = true;
    else if (a !== "--") rest.push(a);
  }
  if (rest[0]) out.route = normalizeRoute(rest[0]);
  if (out.as && !ROLES[out.as]) throw new Error(`--as: ожидается ${Object.keys(ROLES).join("|")}`);
  out.base ??= process.env.SHOT_BASE ?? (out.playground ? "http://localhost:28174" : "http://localhost:28173");
  return out;
}

/** Маршрут без ведущего «/» дополняется; Git Bash превращает `/x` в `C:/Program Files/Git/x` — откатываем. */
export function normalizeRoute(route) {
  const msys = route.match(/^[A-Za-z]:[\\/].*?[\\/]Git([\\/].*)$/);
  const r = (msys ? msys[1] : route).replace(/\\/g, "/");
  return r.startsWith("/") ? r : `/${r}`;
}

/** Демо-логин из tools/seed/config.yaml (раздел demo:); шаблон `{n:02d}` → первый аккаунт. */
export function demoAccount(role, yamlText) {
  const pick = (key) => yamlText.match(new RegExp(`^\\s*${key}:\\s*"([^"]+)"`, "m"))?.[1];
  const email = pick(ROLES[role])?.replace(/\{n:0(\d+)d\}/, (_, w) => "1".padStart(Number(w), "0"));
  const password = pick("password");
  if (!email || !password) throw new Error("В tools/seed/config.yaml нет demo-аккаунта для " + role);
  return { email, password };
}

export function shotName(route, playground) {
  const slug = route.replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "") || "root";
  return playground ? `playground-${slug}` : slug;
}

async function launch() {
  const forced = process.env.SHOT_CHANNEL;
  const tries = forced ? [forced] : [undefined, "msedge", "chrome"];
  let last;
  for (const channel of tries) {
    try {
      return await chromium.launch(channel ? { channel } : {});
    } catch (e) {
      last = e;
    }
  }
  throw new Error(
    "Не найден браузер: `pnpm --filter @fsp/ui exec playwright install chromium` или SHOT_CHANNEL=msedge\n" +
      last?.message,
  );
}

async function login(page, base, role) {
  const acc = demoAccount(role, readFileSync(join(ROOT, "tools/seed/config.yaml"), "utf8"));
  await page.goto(new URL("/login", base).href);
  await page.fill('input[name="email"]', acc.email);
  await page.fill('input[name="password"]', acc.password);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });
}

async function main() {
  const opt = parseArgs(process.argv.slice(2));
  const outDir = join(ROOT, "reports/shots");
  mkdirSync(outDir, { recursive: true });
  const name = opt.name ?? shotName(opt.route, opt.playground);
  const browser = await launch();
  const files = [];
  try {
    for (const theme of THEMES) {
      const ctx = await browser.newContext({ colorScheme: theme, viewport: { width: WIDTHS[0], height: 900 } });
      // Тема приложения хранится в localStorage (shared/lib/theme.tsx), playground читает тот же ключ.
      await ctx.addInitScript((t) => {
        try {
          localStorage.setItem("fsp-theme", t);
        } catch {
          /* нет хранилища — останется системная тема из colorScheme */
        }
      }, theme);
      const page = await ctx.newPage();
      if (opt.as) await login(page, opt.base, opt.as);
      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 900 });
        await page.goto(new URL(opt.route, opt.base).href, { waitUntil: "networkidle" });
        const file = join(outDir, `${name}-${width}-${theme}.png`);
        await page.screenshot({ path: file, fullPage: true });
        files.push(file);
      }
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
  for (const f of files) console.log(f);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => {
    console.error(e.message ?? e);
    process.exit(1);
  });
}
