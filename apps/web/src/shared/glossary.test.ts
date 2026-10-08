import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { GLOSSARY, type GlossaryKey } from "./glossary";

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((n) => {
    const p = join(dir, n);
    if (n === "api") return [];
    if (statSync(p).isDirectory()) return sources(p);
    return /\.tsx$/.test(n) && !/\.test\./.test(n) ? [readFileSync(p, "utf8")] : [];
  });
}

describe("словарь пояснений", () => {
  const code = sources(join(__dirname, "..")).join("\n");
  it.each(Object.keys(GLOSSARY) as GlossaryKey[])("ключ %s используется на экранах", (k) => {
    expect(code).toMatch(new RegExp(`(<Gi|<Gloss) k="${k}"|tip="${k}"`));
  });
  it("тексты короткие, без формул", () => {
    for (const g of Object.values(GLOSSARY)) {
      expect(g.text.split(/[.!?]\s/).length).toBeLessThanOrEqual(2);
      expect(g.text).not.toMatch(/[=∑√]/);
    }
  });
});
