import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { finishedAttempts, parseViews, scatter, viewsSeries } from "./stats-model";
import { plural } from "./text";

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
  preferences: { salary_min: 70000, formats: ["remote"], employment_types: [], city: null, relocation: false },
  visibility: { public_profile: false, teams: true },
  grade: { grade: null, score: null, confidence: null, preliminary: true, breakdown: [] },
  skills: [sk("python", "Python", 3, ["test"]), sk("sql", "SQL", 2, ["test"]), sk("git", "Git", 0, [], true)],
  fsp: { verified: true, achievements: [{ fact_id: "f1", title: "Всероссийский финал по продуктовому программированию", level: "national", year: 2025 }], ranks: [] },
};

const attempt = (id: string, status: string, finished: string | null, mode = "express") => ({
  id,
  profession: "backend",
  declared_grade: "junior",
  stage: "done",
  mode,
  status,
  answered: 10,
  target: 10,
  started_at: "2026-10-01T10:00:00Z",
  finished_at: finished,
});

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
  category_size: 64,
  peers: [
    { strength: 0.64, salary_min: 70000, theta: 0.5 },
    { strength: 0.4, salary_min: 50000, theta: 0 },
    { strength: 0.8, salary_min: 150000, theta: 1 },
    { strength: 0.2, salary_min: null, theta: -1 },
  ],
  category_stats: { candidates: 64, interests: 5, interest_salary_from_median: 160000, interest_salary_to_median: 230000, companies_searching: 4 },
};

const interests = {
  companies: 3,
  salary_from_min: 140000,
  salary_to_max: 220000,
  items: [{ id: "o1", status: "interest" }],
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
    "/candidates/me/standing": () => res(200, standing),
    "/assessment/history": () =>
      res(200, {
        surveys: [],
        attempts: [attempt("a1", "failed", "2026-09-20T10:00:00Z", "full"), attempt("a2", "passed", "2026-10-07T10:05:00Z"), attempt("a3", "active", null)],
        cooldowns: [],
        retries: [],
      }),
    "/candidates/me/views": () => res(200, { total_30d: 7, companies_30d: 3, by_day: [{ date: "2026-10-07", count: 4 }] }),
    "/candidates/me/interests": () => res(200, interests),
    "/candidates/me/navigator": () => res(200, { skill_gaps: [], competitions: [], uplift: [] }),
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

function mount(path = "/me/stats") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

describe("модель Статистики (E38-2)", () => {
  it("точки: X — θ в 0–100 по категории, Y — сила; без θ X — сила; одинаковая θ — посередине", () => {
    const { points, you } = scatter(standing.peers);
    expect(you).toEqual({ x: 75, y: 64 });
    expect(points).toEqual([
      { x: 50, y: 40 },
      { x: 100, y: 80 },
      { x: 0, y: 20 },
    ]);
    expect(scatter([{ strength: 0.5, theta: 1 }, { strength: 0.3, theta: 1 }]).you).toEqual({ x: 50, y: 50 });
    expect(scatter([{ strength: 0.5 }, { strength: 0.3 }]).points).toEqual([{ x: 30, y: 30 }]);
    expect(scatter([], 0.7)).toEqual({ points: [], you: { x: 70, y: 70 } });
  });

  it("просмотры: разбор ответа и ряд по дням до сегодня", () => {
    expect(parseViews({ total_30d: 2, companies_30d: 1, by_day: [{ date: "2026-10-07", count: 2 }, { bad: 1 }] })).toEqual({
      total: 2,
      companies: 1,
      byDay: [{ date: "2026-10-07", count: 2 }],
    });
    expect(parseViews(null)).toBeUndefined();
    const s = viewsSeries([{ date: "2026-10-07", count: 2 }, { date: "2026-10-01", count: 1 }], new Date("2026-10-07T20:00:00Z"), 1);
    expect(s).toEqual([1, 0, 0, 0, 0, 0, 2]);
    expect(viewsSeries([], new Date("2026-10-07T00:00:00Z"))).toHaveLength(35);
  });

  it("история: только завершённые, новые выше; склонение", () => {
    const rows = finishedAttempts([attempt("a", "failed", "2026-09-01T00:00:00Z"), attempt("b", "active", null), attempt("c", "passed", "2026-10-01T00:00:00Z")] as never);
    expect(rows.map((a) => a.id)).toEqual(["c", "a"]);
    expect([1, 3, 5, 11, 21].map((n) => plural(n, "a", "b", "c"))).toEqual(["a", "b", "c", "c", "a"]);
  });
});

describe("Статистика /me/stats (E38-2)", () => {
  it("основное: плитки, «Где ты среди своих», просмотры, «Как тебя видят», ФСП, история", async () => {
    mount();
    const main = await screen.findByTestId("stats-main");
    expect(screen.getByRole("heading", { level: 1, name: "Статистика" })).toBeInTheDocument();

    const tiles = within(main).getByTestId("stats-tiles");
    expect(tiles).toHaveTextContent("78 %");
    expect(tiles).toHaveTextContent("От лидера категории");
    expect(tiles).toHaveTextContent("до топ-20 % не хватает 6.5 п. п.");
    expect(within(tiles).getByTestId("gi-strength")).toBeInTheDocument();
    expect(within(main).getByTestId("stats-parts")).toHaveTextContent("Уровень в тесте");
    expect(tiles).toHaveTextContent("140–220");
    expect(await within(tiles).findByText("за 30 дней")).toBeInTheDocument();

    const peers = screen.getByTestId("stats-peers");
    expect(peers).toHaveTextContent("64 чел.");
    expect(within(peers).getByRole("img", { name: "Точечная диаграмма категории Backend Junior" })).toBeInTheDocument();
    expect(peers.querySelector("[data-you]")).not.toBeNull();
    expect(within(peers).getByText("уровень в тесте →")).toBeInTheDocument();
    expect(within(peers).getByText("↑ сила профиля")).toBeInTheDocument();
    expect(within(peers).getByTestId("gi-peers")).toBeInTheDocument();
    expect(within(peers).getByTestId("stats-peers-note")).toHaveTextContent("Свои — кандидаты категории Backend Junior");
    expect(within(peers).getByTestId("gi-theta")).toBeInTheDocument();

    const cat = within(main).getByTestId("stats-category");
    expect(cat).toHaveTextContent("Кандидатов в категории");
    expect(cat).toHaveTextContent("64");
    expect(cat).toHaveTextContent("160–230");
    expect(cat).toHaveTextContent("медиана по 5 интересам");
    expect(cat).toHaveTextContent("Компаний ищут категорию");
    expect(cat).toHaveTextContent("4");

    const views = await screen.findByTestId("stats-views");
    expect(within(views).getByRole("img", { name: /7 за 30 дней/ })).toBeInTheDocument();
    expect(views).toHaveTextContent("3 компании смотрели за 30 дней");

    const seen = screen.getByTestId("stats-seen-as");
    expect(seen).toHaveTextContent("Backend #4821");
    expect(seen).toHaveTextContent("подтверждён ФСП");
    expect(seen).toHaveTextContent("Junior · Backend · Python");
    expect(within(seen).getByText("Git").closest("[data-state]")).toHaveAttribute("data-state", "claimed");
    expect(seen).toHaveTextContent("от 70 000");

    expect(screen.getByTestId("stats-fsp")).toHaveTextContent("Всероссийский финал");

    const hist = await screen.findByTestId("stats-history");
    const rows = within(hist).getAllByTestId("stats-attempt");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("подтверждён");
    expect(rows[0]).toHaveTextContent("экспресс · 07.10");
    expect(rows[1]).toHaveTextContent("не подтверждён");
    expect(rows[1]).toHaveTextContent("полный · 20.09");

    // Одна главная кнопка — следующий шаг: есть интерес без ответа.
    const action = await screen.findByTestId("stats-action");
    expect(await within(action).findByText("Ответить на интерес")).toBeInTheDocument();
    expect(action).toHaveAttribute("href", "/me/offers?show=interests");
  });

  it("без теста — пустое состояние с одной кнопкой «Пройти тест»", async () => {
    routes["/candidates/me/standing"] = () => res(200, { peers: [], category_size: 0 });
    mount();
    expect(await screen.findByText("Статистики пока нет")).toBeInTheDocument();
    expect(screen.getByTestId("stats-empty-action")).toHaveAttribute("href", "/me/assessment");
    expect(screen.queryByTestId("stats-main")).not.toBeInTheDocument();
    expect(screen.queryByTestId("stats-action")).not.toBeInTheDocument();
  });

  it("без интересов и без category_stats — вилка «нет данных», блок скрыт", async () => {
    routes["/candidates/me/standing"] = () => res(200, { ...standing, category_stats: { ...standing.category_stats, interests: 0, interest_salary_from_median: null, interest_salary_to_median: null } });
    mount();
    const cat = await screen.findByTestId("stats-category");
    expect(cat).toHaveTextContent("компании пока не отмечали интерес");
    cleanup();
    routes["/candidates/me/standing"] = () => res(200, { ...standing, category_stats: null });
    mount();
    await screen.findByTestId("stats-main");
    expect(screen.queryByTestId("stats-category")).not.toBeInTheDocument();
  });

  it("загрузка — скелетон; ошибка — код и «Повторить»", async () => {
    let fail = true;
    routes["/candidates/me/standing"] = () => (fail ? res(503, { code: "unavailable" }) : res(200, standing));
    mount();
    expect(await screen.findByTestId("stats-loading")).toBeInTheDocument();
    const err = await screen.findByTestId("stats-error", undefined, { timeout: 5000 });
    expect(err).toHaveTextContent("Не загрузилось");
    expect(err).toHaveTextContent("ошибка 503");
    fail = false;
    within(err).getByRole("button", { name: "Повторить" }).click();
    expect(await screen.findByTestId("stats-main")).toBeInTheDocument();
  });
});
