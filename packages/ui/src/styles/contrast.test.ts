import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/styles/tokens.css", "utf8");
const block = (sel: string) => css.split(sel)[1]?.split("}")[0] ?? "";
const vars = (b: string) => Object.fromEntries([...b.matchAll(/--([\w-]+):\s*(#[0-9a-f]{3,6})\b/gi)].map((m) => [m[1], m[2]]));
const light = vars(block(":root {"));
const dark = { ...light, ...vars(block(".dark {")) };

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

describe("контраст пар (brand.md §3)", () => {
  it("светлая: brand-fg определён и равен brand", () => {
    expect(light["brand-fg"]).toBe(light.brand);
  });
  it.each([
    ["ink", "page"],
    ["muted", "page"],
    ["brand-fg", "card"],
    ["on-brand", "brand"],
    ["error", "error-bg"],
    ["success", "success-bg"],
    ["warning-fg", "warning-bg"],
  ])("светлая %s на %s >= 4.5", (fg, bg) => {
    expect(ratio(light[fg], light[bg])).toBeGreaterThanOrEqual(4.5);
  });
  it.each([
    ["ink", "page"],
    ["muted", "page"],
    ["brand-fg", "page"],
    ["brand-fg", "card"],
    ["error", "error-bg"],
    ["success", "success-bg"],
    ["warning-fg", "warning-bg"],
  ])("тёмная %s на %s >= 4.5", (fg, bg) => {
    expect(ratio(dark[fg], dark[bg])).toBeGreaterThanOrEqual(4.5);
  });
});
