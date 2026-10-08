import appSource from "./App.tsx?raw";
import { NAV, ROUTES, activeNav, type NavItem } from "./routes";

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

  // E35-1: нет пункта меню, ссылки или кнопки без работающего экрана.
  const items = (nav: NavItem[]) => nav.flatMap((n) => [n, ...(n.tabs ?? [])]);
  const all = Object.values(NAV).flatMap(items);
  const byPath = new Map(ROUTES.map((r) => [r.path, r]));

  it("у каждого маршрута есть страница или переадресация (заглушек нет)", () => {
    for (const r of ROUTES) {
      if (r.redirect) {
        const target = r.redirect.split("?")[0];
        expect(byPath.get(target)?.redirect, `${r.path} → ${r.redirect}`).toBeUndefined();
        expect(byPath.has(target), r.redirect).toBe(true);
      } else {
        expect(appSource, `${r.path} подключён в App.tsx`).toContain(`path="${r.path}"`);
      }
    }
    expect(appSource).not.toMatch(/Stub/);
  });

  it("каждый пункт меню и вкладка ведут на реализованный экран с nav", () => {
    for (const item of all) {
      const r = byPath.get(item.to);
      expect(r, item.to).toBeDefined();
      expect(r?.nav, item.to).toBe(true);
      expect(r?.redirect, item.to).toBeUndefined();
    }
  });

  it("nav в routes помечает только то, что есть в меню", () => {
    const inMenu = new Set(all.map((i) => i.to));
    for (const r of ROUTES.filter((x) => x.nav)) expect(inMenu.has(r.path), r.path).toBe(true);
  });

  it("меню: кандидат и работодатель по ux-spec, админ не больше 6 пунктов", () => {
    expect(NAV.candidate.map((n) => n.label)).toEqual(["Главная", "Тест и грейд", "Вакансии", "Приглашения", "Профиль"]);
    // «Шорт-лист» добавится вместе с общим экраном (E35-4): без экрана пункта нет.
    expect(NAV.employer.map((n) => n.label)).toEqual(["Подбор", "Шорт-лист", "Приглашения", "Компания"]);
    expect(NAV.admin.length).toBeLessThanOrEqual(6);
  });

  it("подсветка пункта меню по самому длинному префиксу", () => {
    expect(activeNav(NAV.candidate, "/me")?.label).toBe("Главная");
    expect(activeNav(NAV.candidate, "/me/skills/python")?.label).toBe("Главная");
    expect(activeNav(NAV.candidate, "/me/assessment/attempts/1")?.label).toBe("Тест и грейд");
    expect(activeNav(NAV.candidate, "/me/interests")?.label).toBe("Приглашения");
    expect(activeNav(NAV.candidate, "/me/profile/edit")?.label).toBe("Профиль");
    expect(activeNav(NAV.employer, "/employer/needs/7")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer/categories/backend/middle")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer/responses")?.label).toBe("Приглашения");
    expect(activeNav(NAV.employer, "/employer/subscriptions")?.label).toBe("Компания");
    expect(activeNav(NAV.employer, "/employer/vacancies/1/shortlist")?.label).toBe("Компания");
    expect(activeNav(NAV.admin, "/federation/moderation")?.label).toBe("Модерация");
  });
});
