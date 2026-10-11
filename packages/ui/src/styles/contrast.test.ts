import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/styles/tokens.css", "utf8");
// Правила tokens.css: селектор (без комментариев) и тело. Значения одной темы сливаются по порядку правил.
const rules = css
  .replace(/\/\*[\s\S]*?\*\//g, "")
  .split("}")
  .map((r) => r.split("{"))
  .filter((p) => p.length === 2)
  .map(([sel, body]) => ({ sel: sel.replace(/\s+/g, " ").trim(), body }));
const body = (...sels: string[]) => rules.filter((r) => sels.includes(r.sel)).map((r) => r.body).join(" ");
const vars = (b: string) => Object.fromEntries([...b.matchAll(/--([\w-]+):\s*(#[0-9a-f]{3,6})/gi)].map((m) => [m[1], m[2]]));
// Алиасы `--chip-fg: var(--brand-deep)` раскрываются в своей теме.
const alias = (t: Record<string, string>, b: string) => {
  for (const m of b.matchAll(/--([\w-]+):\s*var\(--([\w-]+)\)/g)) t[m[1]] = t[m[2]];
  return t;
};
const shared = body(":root, .dark, .light");
const light = alias(vars(body(":root", ":root, .dark, .light")), shared);
const darkOwn = vars(body(".dark"));
const dark = { ...alias({ ...light }, shared.replace(/--([\w-]+):\s*var\(--[\w-]+\)/g, (m, k) => (k in darkOwn ? "" : m))), ...darkOwn };

function lum(hex: string) {
  const h = hex.length === 4 ? [...hex.slice(1)].map((c) => c + c).join("") : hex.slice(1);
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = parseInt(h.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const ratio = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

// Пары «текст на фоне» для обеих тем: всё, что реально встречается на экранах (текст ≥ 4.5).
const TEXT_ON: Array<[string, string]> = [
  ["ink", "page"],
  ["ink", "card"],
  ["ink", "tint-50"],
  ["muted", "page"],
  ["muted", "card"],
  ["muted", "tint-50"],
  ["brand-fg", "page"],
  ["brand-fg", "card"],
  ["brand-fg", "tint-50"],
  ["brand-fg", "tint-100"],
  ["chip-fg", "tint-100"],
  ["signal", "page"],
  ["signal", "card"],
  ["error", "page"],
  ["error", "card"],
  ["error", "error-bg"],
  ["success", "page"],
  ["success", "card"],
  ["success", "success-bg"],
  ["warning-fg", "warning-bg"],
  ["on-brand", "brand"],
];

describe("контраст пар", () => {
  it("светлая: brand-fg определён и равен brand", () => {
    expect(light["brand-fg"]).toBe(light.brand);
  });
  it.each(TEXT_ON)("светлая %s на %s >= 4.5", (fg, bg) => {
    expect(ratio(light[fg], light[bg])).toBeGreaterThanOrEqual(4.5);
  });
  it.each(TEXT_ON)("тёмная %s на %s >= 4.5", (fg, bg) => {
    expect(ratio(dark[fg], dark[bg])).toBeGreaterThanOrEqual(4.5);
  });
  it("тёмная: граница отличима от фона карточки (>= 1.2)", () => {
    expect(ratio(dark.hairline, dark.card)).toBeGreaterThanOrEqual(1.2);
  });
});
