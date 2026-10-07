#!/usr/bin/env node
// PNG всех макетов v2 (E38-0): docs/design/v2/screens/*.html → docs/design/v2/png/<имя>.png.
//   pnpm --filter @fsp/ui design-shots [--only <подстрока>] [--out <каталог>]
// Размер кадра — ширина и высота из docs/design/v2/screens.json (у доски компонентов — по содержимому).
// Шрифты макеты берут с Google Fonts: без сети снимки будут с системным шрифтом.
// Браузер: Chromium Playwright; если его нет — системный Edge или Chrome (SHOT_CHANNEL=msedge|chrome).
import { existsSync, mkdirSync, readFileSync, readdirSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { chromium } from "playwright";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const V2 = join(ROOT, "docs/design/v2");

/** Список экранов: всё из screens/*.html; размеры — из screens.json, иначе ширина из имени (`_375`). */
export function screenList(files, meta) {
  const byFile = new Map(meta.map((m) => [basename(m.file), m]));
  return files
    .filter((f) => f.endsWith(".html"))
    .sort()
    .map((f) => {
      const m = byFile.get(f);
      const w = m?.width ?? Number(f.match(/_(\d{3,4})\.html$/)?.[1] ?? 1440);
      return { file: f, png: f.replace(/\.html$/, ".png"), width: w, height: m?.height ?? 800 };
    });
}

function parseArgs(argv) {
  const out = { only: null, out: join(V2, "png") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--only") out.only = argv[++i];
    else if (argv[i] === "--out") out.out = resolve(argv[++i]);
  }
  return out;
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
  throw new Error("Не найден браузер: `pnpm --filter @fsp/ui exec playwright install chromium` или SHOT_CHANNEL=msedge\n" + last?.message);
}

async function main() {
  const opt = parseArgs(process.argv.slice(2));
  const meta = existsSync(join(V2, "screens.json")) ? JSON.parse(readFileSync(join(V2, "screens.json"), "utf8")) : [];
  let list = screenList(readdirSync(join(V2, "screens")), meta);
  if (opt.only) list = list.filter((s) => s.file.includes(opt.only));
  mkdirSync(opt.out, { recursive: true });
  const browser = await launch();
  try {
    for (const width of [...new Set(list.map((s) => s.width))]) {
      const ctx = await browser.newContext({ viewport: { width, height: 800 }, deviceScaleFactor: 1 });
      const page = await ctx.newPage();
      for (const s of list.filter((x) => x.width === width)) {
        await page.setViewportSize({ width, height: s.height });
        await page.goto(pathToFileURL(join(V2, "screens", s.file)).href, { waitUntil: "load" });
        await page.evaluate("document.fonts         await page.evaluate(() => document.fonts?.ready);        await page.evaluate(() => document.fonts?.ready); document.fonts.ready");
        await page.screenshot({ path: join(opt.out, s.png), fullPage: true });
        console.log(s.png);
      }
      await ctx.close();
    }
  } finally {
    await browser.close();
  }
  console.log(`${list.length} PNG → ${opt.out}`);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => {
    console.error(e.message ?? e);
    process.exit(1);
  });
}
