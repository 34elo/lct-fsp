import { NAV, ROUTES } from "./routes";

const segs = (p: string) => p.split("/").filter(Boolean);
const isParam = (s: string) => s.startsWith(":");

describe("routes", () => {
  it("пути уникальны", () => {
    const paths = ROUTES.map((r) => r.path);
    expect(paths.filter((p, i) => paths.indexOf(p) !== i)).toEqual([]);
  });

  it("у каждого маршрута есть владелец", () => {
    for (const r of ROUTES) expect(["b1", "b2"], r.path).toContain(r.owner);
  });

  it("конкретные пути объявлены раньше параметрических", () => {
    ROUTES.forEach((a, i) => {
      const sa = segs(a.path);
      ROUTES.slice(i + 1).forEach((b) => {
        const sb = segs(b.path);
        if (sa.length !== sb.length) return;
        const covers = sa.every((s, k) => isParam(s) || s === sb[k]);
        const stricter = sa.some((s, k) => isParam(s) && !isParam(sb[k]));
        expect(covers && stricter, `${a.path} раньше ${b.path}`).toBe(false);
      });
    });
  });

  it("существующее меню NAV помечено nav в routes", () => {
    const flagged = new Set(ROUTES.filter((r) => r.nav).map((r) => r.path));
    for (const item of Object.values(NAV).flat()) expect(flagged.has(item.to), item.to).toBe(true);
  });
});
