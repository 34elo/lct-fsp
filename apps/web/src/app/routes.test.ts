import appSource from "./App.tsx?raw";
import { ADMIN_GROUPS, NAV, ROUTES, activeNav, type NavItem } from "./routes";

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
  const items = (nav: NavItem[]) => nav;
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

  it("меню без подвкладок: кандидат и работодатель по E39-25", () => {
    expect(NAV.candidate.map((n) => n.label)).toEqual(["Главная", "Тест", "Приглашения", "Вакансии", "Статистика", "Профиль"]);
    expect(NAV.employer.map((n) => n.label)).toEqual(["Подбор", "Шорт-лист", "Приглашения", "Вакансии", "Задания", "Компания"]);
    for (const n of Object.values(NAV).flat()) expect(n, n.label).not.toHaveProperty("tabs");
    for (const n of [...NAV.candidate, ...NAV.employer]) expect(n, n.label).not.toHaveProperty("group");
  });

  it("меню админа (E39-29): «Главная», затем группы Очереди · Справочники · Аналитика, в группе не больше 4 пунктов", () => {
    const [home, ...rest] = NAV.admin;
    expect(home).toEqual({ to: "/federation", label: "Главная" });
    expect(ADMIN_GROUPS.map((g) => g.label)).toEqual(["Очереди", "Справочники", "Аналитика"]);
    // пункты идут группами в порядке ADMIN_GROUPS, без «висящих» пунктов
    const order = ADMIN_GROUPS.map((g) => g.id);
    const seen = rest.map((n) => order.indexOf(n.group!));
    expect(seen.every((g) => g >= 0)).toBe(true);
    expect(seen).toEqual([...seen].sort((a, b) => a - b));
    for (const g of order) {
      const n = rest.filter((x) => x.group === g).length;
      expect(n, g).toBeGreaterThan(0);
      expect(n, g).toBeLessThanOrEqual(4);
    }
    const by = (g: string) => rest.filter((n) => n.group === g).map((n) => n.label);
    expect(by("queues")).toEqual(["Заявки ФСП", "Допуск заданий", "Модерация"]);
    expect(by("refs")).toEqual(["Реестр ФСП", "Профессии", "Граф навыков"]);
    expect(by("analytics")).toEqual(["Воронка", "Качество"]);
  });

  it("подсветка пункта меню по самому длинному префиксу", () => {
    expect(activeNav(NAV.candidate, "/me")?.label).toBe("Главная");
    expect(activeNav(NAV.candidate, "/me/skills/python")?.label).toBe("Главная");
    expect(activeNav(NAV.candidate, "/me/assessment/attempts/1")?.label).toBe("Тест");
    expect(activeNav(NAV.candidate, "/me/interests")?.label).toBe("Приглашения");
    expect(activeNav(NAV.candidate, "/me/profile/edit")?.label).toBe("Профиль");
    expect(activeNav(NAV.employer, "/employer/needs/7")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer/categories/backend/middle")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer/responses")?.label).toBe("Приглашения");
    expect(activeNav(NAV.employer, "/employer/subscriptions")?.label).toBe("Подбор");
    expect(activeNav(NAV.employer, "/employer/vacancies/1/shortlist")?.label).toBe("Вакансии");
    expect(activeNav(NAV.employer, "/employer/families/new")?.label).toBe("Задания");
    expect(activeNav(NAV.candidate, "/me/tasks")?.label).toBe("Главная"); // задания — с Главной (E39-15)
    expect(activeNav(NAV.candidate, "/onboarding")).toBeUndefined(); // онбординга в меню нет (E39-15)
    expect(activeNav(NAV.candidate, "/me/stats")?.label).toBe("Статистика");
    expect(activeNav(NAV.admin, "/federation/moderation")?.label).toBe("Модерация");
    expect(activeNav(NAV.admin, "/federation")?.label).toBe("Главная");
    expect(activeNav(NAV.admin, "/federation/registry")?.label).toBe("Реестр ФСП");
    expect(activeNav(NAV.admin, "/federation/requests")?.label).toBe("Заявки ФСП");
    expect(activeNav(NAV.admin, "/admin/quality/runs")?.label).toBe("Качество");
  });
});
