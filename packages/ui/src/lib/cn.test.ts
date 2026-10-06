import { cn } from "./cn";

test("размер из шкалы токенов не теряется рядом с цветом текста", () => {
  expect(cn("text-11 text-muted")).toBe("text-11 text-muted");
  expect(cn("text-13 text-brand-fg", "text-ink")).toBe("text-13 text-ink");
});

test("последний размер побеждает", () => {
  expect(cn("text-11", "text-16")).toBe("text-16");
});
