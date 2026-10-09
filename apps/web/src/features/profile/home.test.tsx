import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { constellationNodes, formatsText, latestInvites, nextStep, ratingText, skillSource } from "./home-model";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const sk = (slug: string, name: string, level: number, sources: string[], claimed_only = false) => ({
  skill: { slug, name, group: "language" },
  confidence: level / 4,
  level,
  sources,
  claimed_only,
  status: "active",
  top_evidence: [],
});

const profile = {
  pseudonym: "Backend #4821",
  profile_version: 3,
  search_status: "active",
  active_until: null,
  preferences: { salary_min: 70000, formats: ["remote", "hybrid"], employment_types: [], city: "Санкт-Петербург", relocation: false },
  visibility: { public_profile: false, teams: true },
  grade: { grade: null, score: null, confidence: null, preliminary: true, breakdown: [] },
  skills: [sk("python", "Python", 3, ["test"]), sk("sql", "SQL", 2, ["test"]), sk("git", "Git", 0, [], true)],
  fsp: { verified: true, achievements: [{ fact_id: "f1", title: "Всероссийский финал по продуктовому программированию", level: "national", year: 2025 }], ranks: [] },
  claimed_vs_confirmed: [{ profession: "backend", declared_grade: "junior", confirmed_grade: "junior", status: "confirmed" }],
};

const passed = {
  id: "a1",
  profession: "backend",
  declared_grade: "junior",
  stage: "done",
  mode: "express",
  status: "passed",
  answered: 10,
  target: 10,
  started_at: "2026-10-07T10:00:00Z",
  finished_at: "2026-10-07T10:05:00Z",
};
const survey = { id: "s1", profession: "backend", stack: ["Python", "Docker"], created_at: "2026-10-07T09:00:00Z" };

const standing = {
  profession: "backend",
  grade: "junior",
  mode: "express",
  confirmed_at: "2026-10-07T10:05:00Z",
  strength: {
    value: 0.64,
    rank: 3,
    top_percent: 30,
    relative: 78,
    gap_to_next_ten: { top_percent: 20, gap_relative: 6.5 },
    parts: [{ code: "T", text: "Уровень в тесте", value: 0.7, weight: 0.4 }],
  },
  category_size: 10,
  peers: [],
};

const offer = (id: string, company: string, from: number, to: number, status = "interest") => ({
  id,
  status,
  created_at: "2026-10-07T00:00:00Z",
  expires_at: "2026-10-20T00:00:00Z",
  salary_from: from,
  salary_to: to,
  below_candidate_min: false,
  company: { id: `c-${id}`, name: company, verified: true, responsibility_score: 0.92 },
  why_you: { factors: [{ code: "skills", text: "Python, SQL — подтверждено тестом", weight: 0.9 }], unconfirmed: [] },
});

const interests = {
  companies: 3,
  salary_from_min: 140000,
  salary_to_max: 220000,
  items: [offer("o1", "Северный код", 150000, 220000), offer("o2", "Кедр Софт", 140000, 190000), offer("o3", "Сигма Лаб", 160000, 200000), offer("o4", "Четвёртая", 100000, 120000)],
};

const navigator = {
  test: { profession: "backend", grade: "middle", path: "/me/assessment?profession=backend&grade=middle" },
  skill_gaps: [{ skill: "docker", name: "Docker", weight: 1, confidence: 0, testable: true }],
  competitions: [],
  uplift: [],
};

type Routes = Record<string, () => Response>;
let routes: Routes = {};

class NoES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("EventSource", NoES);
  setAccessToken(null);
  routes = {
    "/candidates/me/profile": () => res(200, profile),
    "/assessment/history": () => res(200, { surveys: [survey], attempts: [passed], cooldowns: [], retries: [] }),
    "/candidates/me/standing": () => res(200, standing),
    "/candidates/me/interests": () => res(200, interests),
    "/candidates/me/offers": () => res(200, [{ ...offer("o9", "Новая компания", 170000, 230000, "sent"), created_at: "2026-10-08T00:00:00Z" }]),
    "/candidates/me/navigator": () => res(200, navigator),
    "/candidates/me/views": () => res(200, { total_30d: 5, companies_30d: 2, by_day: [{ date: "2026-10-07", count: 5 }] }),
    "/taxonomy/professions": () => res(200, { professions: [{ slug: "backend", title: "Backend" }] }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      const path = new URL(url, "http://x").pathname.replace(/^\/api\/v1/, "");
      if (path === "/me" || path === "/auth/me") return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      const h = routes[path];
      return h ? h() : res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(path = "/me") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

describe("модель Главной (E38-1)", () => {
  it("latestInvites: объединяет, убирает дубли и отклики кандидата, берёт 3 свежих", () => {
    const o = (id: string, d: string, initiator?: string) => ({ ...offer(id, id, 1, 2), created_at: d, initiator }) as never;
    const r = latestInvites([o("a", "2026-10-01"), o("b", "2026-10-05")], [o("b", "2026-10-05"), o("c", "2026-10-06"), o("d", "2026-10-09", "candidate"), o("e", "2026-10-02")]);
    expect(r.map((x) => x.id)).toEqual(["c", "b", "e"]);
  });

  it("следующий шаг: первый не пройденный, интерес — только при интересах без ответа", () => {
    const a = nextStep({ tested: true, fspLinked: true, pendingInterests: 2, nextTest: { grade: "Middle", path: "/x" } });
    expect(a.steps.map((s) => [s.label, s.state])).toEqual([
      ["Тест пройден", "done"],
      ["ФСП привязан", "done"],
      ["Ответить на интерес", "current"],
      ["Тест на Middle", "future"],
    ]);
    expect(a.current).toEqual({ key: "interest", label: "Ответить на интерес", to: "/me/offers?show=interests" });

    const b = nextStep({ tested: true, fspLinked: false, pendingInterests: 0 });
    expect(b.steps.map((s) => s.id)).toEqual(["test", "fsp"]);
    expect(b.current).toEqual({ key: "fsp", label: "Привязать ФСП", to: "/me/profile?tab=data" });

    const c = nextStep({ tested: true, fspLinked: true, pendingInterests: 0, nextTest: { grade: "Middle", path: "/x" } });
    expect(c.current).toEqual({ key: "next", label: "Пройти тест на Middle", to: "/x" });
    expect(nextStep({ tested: true, fspLinked: true, pendingInterests: 0 }).current).toBeNull();
    expect(nextStep({ tested: false, fspLinked: true, pendingInterests: 0 }).current?.key).toBe("test");
  });

  it("созвездие: подтверждённые выше заявленных, стек опроса и смежные без дублей", () => {
    const nodes = constellationNodes([sk("git", "Git", 0, [], true), sk("python", "Python", 3, ["test"])], { stack: ["python", "Docker"], adjacent: ["Docker", "REST"] });
    expect(nodes).toEqual([
      { name: "Python", level: 3, state: "confirmed" },
      { name: "Git", level: 0, state: "claimed" },
      { name: "Docker", level: 0, state: "claimed" },
      { name: "REST", level: 0, state: "adjacent" },
    ]);
    expect(constellationNodes([sk("python", "Python", 3, ["test"])], { claimedOnly: true })[0]).toEqual({ name: "Python", level: 0, state: "claimed" });
  });

  it("форматы, рейтинг, источник навыка", () => {
    expect(formatsText(["remote", "hybrid"])).toBe("Удалёнка или гибрид");
    expect(formatsText([])).toBe("");
    expect(ratingText(0.92)).toBe("4.6 / 5");
    expect(ratingText(4.4)).toBe("4.4 / 5");
    expect(ratingText(null)).toBeUndefined();
    expect(skillSource(sk("p", "P", 3, ["resume", "test"]))).toEqual({ text: "тест", claimed: false });
    expect(skillSource(sk("g", "G", 0, [], true))).toEqual({ text: "заявлен", claimed: true });
  });
});

describe("Главная кандидата /me (E38-1)", () => {
  it("после теста: профиль, навыки, ФСП, следующий шаг, созвездие, интересы, плитки", async () => {
    mount();
    const after = await screen.findByTestId("home-after");
    expect(screen.getByRole("heading", { level: 1, name: "Главная" })).toBeInTheDocument();

    const prof = within(after).getByTestId("home-profile");
    expect(prof).toHaveTextContent("Backend #4821");
    expect(prof).toHaveTextContent("Санкт-Петербург");
    expect(await within(prof).findByTestId("home-grade")).toHaveTextContent("Junior · Backend");
    expect(within(prof).getByTestId("home-grade-status")).toHaveTextContent("подтверждён 07.10 · экспресс");
    expect(prof).toHaveTextContent("Удалёнка или гибрид");

    const skills = screen.getByTestId("home-skills");
    expect(skills).toHaveTextContent("Python");
    expect(within(skills).getAllByText("тест")).toHaveLength(2);
    expect(within(skills).getByText("заявлен").closest("[data-state]")).toHaveAttribute("data-state", "claimed");
    expect(screen.getByTestId("home-fsp")).toHaveTextContent("Всероссийский финал");

    const next = await screen.findByTestId("home-next");
    expect(await within(next).findByText(/Тест на Middle/)).toBeInTheDocument();
    expect(next).toHaveAttribute("data-step", "interest");
    const action = screen.getByTestId("home-next-action");
    expect(action).toHaveTextContent("Ответить на интерес");
    expect(action).toHaveAttribute("href", "/me/offers?show=interests");

    expect(screen.getByRole("img", { name: /Созвездие навыков: Python, SQL, Git, Docker/ })).toBeInTheDocument();

    const ints = screen.getByTestId("home-interests");
    expect(within(ints).getAllByTestId("home-invite")).toHaveLength(3);
    expect(ints).toHaveTextContent("3 · 140–220");
    expect(ints).toHaveTextContent("Северный код");
    expect(ints).toHaveTextContent("150–220");
    // Приглашение (не интерес) попадает в список и ведёт на карточку; «Все приглашения» — на список.
    const inv = within(ints).getByRole("link", { name: /Новая компания/ });
    expect(inv).toHaveAttribute("href", "/me/offers/o9");
    expect(within(ints).getByTestId("home-invites-all")).toHaveAttribute("href", "/me/offers");
    // Навыков 4 (≤ 8) — ссылки «Все навыки» нет.
    expect(screen.queryByTestId("home-skills-all")).not.toBeInTheDocument();

    const tiles = screen.getByTestId("home-tiles");
    expect(tiles).toHaveTextContent("Топ-30 %");
    expect(tiles).toHaveTextContent("Backend Junior");
    expect(tiles).not.toHaveTextContent("64");
    expect(within(tiles).getByRole("meter", { name: "Место" })).toHaveAttribute("aria-valuenow", "70");

    // Ссылка «Статистика» (E38-2) со счётчиком компаний, смотревших профиль; баннера пути на Главной нет.
    const stats = screen.getByTestId("home-stats");
    expect(stats).toHaveAttribute("href", "/me/stats");
    expect(await within(stats).findByText("смотрели: 2 ›")).toBeInTheDocument();
    expect(screen.queryByTestId("path-banner")).not.toBeInTheDocument();
  });

  it("грейд не подтверждён: пунктирный грейд и шаг «Пройти тест»", async () => {
    routes["/assessment/history"] = () => res(200, { surveys: [survey], attempts: [{ ...passed, status: "failed" }], cooldowns: [], retries: [] });
    routes["/candidates/me/standing"] = () => res(200, { peers: [], category_size: 0 });
    routes["/candidates/me/interests"] = () => res(200, { companies: 0, items: [] });
    routes["/candidates/me/offers"] = () => res(200, []);
    routes["/candidates/me/navigator"] = () => res(200, { skill_gaps: [], competitions: [], uplift: [] });
    mount();
    expect(await screen.findByTestId("home-grade-status")).toHaveTextContent("не подтверждён");
    expect(screen.getByTestId("home-grade")).toHaveAttribute("data-state", "claimed");
    expect(await screen.findByTestId("home-next-action")).toHaveTextContent("Пройти тест");
    expect(screen.getByTestId("home-tiles")).toHaveTextContent("—");
    expect(screen.queryByTestId("home-interests")).not.toBeInTheDocument();
  });

  it("навыков больше 8: показаны 8 сильнейших и ссылка «Все навыки» в профиль", async () => {
    const many = Array.from({ length: 10 }, (_, i) => sk(`s${i}`, `Навык ${i}`, 1 + (i % 3), ["test"]));
    routes["/candidates/me/profile"] = () => res(200, { ...profile, skills: many });
    mount();
    const card = await screen.findByTestId("home-skills");
    expect(within(card).getAllByText(/^Навык [0-9]$/)).toHaveLength(8);
    expect(within(card).getByTestId("home-skills-all")).toHaveAttribute("href", "/me/profile?tab=skills");
  });

  it("кулдаун следующего грейда: дата следующей попытки", async () => {
    routes["/assessment/history"] = () =>
      res(200, { surveys: [survey], attempts: [passed], cooldowns: [{ profession: "backend", grade: "middle", next_change_at: "2099-10-14T00:00:00Z" }], retries: [] });
    routes["/candidates/me/interests"] = () => res(200, { companies: 0, items: [] });
    mount();
    expect(await screen.findByTestId("home-cooldown")).toHaveTextContent("Следующая попытка — 14.10");
    expect(screen.getByTestId("home-next-action")).toHaveAttribute("href", "/me/assessment?profession=backend&grade=middle");
  });

  it("до теста: одна карточка, созвездие заявленных навыков, одна кнопка в опрос", async () => {
    routes["/assessment/history"] = () => res(200, { surveys: [], attempts: [], cooldowns: [], retries: [] });
    mount();
    const card = await screen.findByTestId("home-before");
    expect(card).toHaveAttribute("data-step", "survey");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Пройди тест — без него тебя не видят работодатели");
    expect(within(card).getByRole("img", { name: "Заявленные навыки без подтверждения" })).toBeInTheDocument();
    const links = within(card).getAllByRole("link");
    expect(new Set(links.map((l) => l.getAttribute("href")))).toEqual(new Set(["/me/assessment"]));
    expect(links[0]).toHaveTextContent("Пройти тест");
    expect(card).toHaveTextContent("экспресс · 3–5 мин");
    expect(screen.queryByTestId("home-after")).not.toBeInTheDocument();
    expect(screen.queryByTestId("path-banner")).not.toBeInTheDocument();
  });

  it("до теста, идёт попытка — «Продолжить тест»", async () => {
    routes["/assessment/history"] = () => res(200, { surveys: [survey], attempts: [{ ...passed, status: "active", finished_at: null }], cooldowns: [], retries: [] });
    mount();
    const card = await screen.findByTestId("home-before");
    expect(card).toHaveAttribute("data-step", "continue");
    expect(within(card).getAllByRole("link")[0]).toHaveAttribute("href", "/me/assessment/attempts/a1");
    expect(within(card).getAllByRole("link")[0]).toHaveTextContent("Продолжить тест");
  });

  it("регулярные задания (E39-15): открытые — блок на Главной, без заданий — блока нет", async () => {
    const task = (id: string, extra: object = {}) => ({ id, title: `Задание ${id}`, kind: "choice", profession: "backend", grade: "middle", answer_until: "2999-01-01T00:00:00Z", submitted: false, score: null, ...extra });
    routes["/assessment/tasks"] = () => res(200, [task("t1"), task("t2", { submitted: true }), task("t3", { answer_until: "2000-01-01T00:00:00Z" })]);
    mount();
    const card = await screen.findByTestId("home-tasks");
    expect(within(card).getAllByTestId("home-task")).toHaveLength(1);
    expect(within(card).getByRole("link", { name: /Задание t1/ })).toHaveAttribute("href", "/me/tasks?task=t1");
    expect(within(card).getByTestId("home-tasks-all")).toHaveAttribute("href", "/me/tasks");
  });

  it("регулярных заданий нет — блока нет", async () => {
    routes["/assessment/tasks"] = () => res(200, []);
    mount();
    expect(await screen.findByTestId("home-after")).toBeInTheDocument();
    expect(screen.queryByTestId("home-tasks")).not.toBeInTheDocument();
  });

  it("загрузка — скелетон; ошибка профиля — «Повторить»", async () => {
    let fail = true;
    routes["/candidates/me/profile"] = () => (fail ? res(500, { code: "internal" }) : res(200, profile));
    mount();
    expect(await screen.findByTestId("home-loading")).toBeInTheDocument();
    const err = await screen.findByTestId("home-error", undefined, { timeout: 5000 });
    fail = false;
    within(err).getByRole("button", { name: "Повторить" }).click();
    expect(await screen.findByTestId("home-after")).toBeInTheDocument();
  });
});
