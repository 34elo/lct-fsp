import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import Fairness from "./Fairness";
import Quality from "./Quality";
import Runs from "./Runs";
import { report } from "./report";
import { T } from "./text";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ code: "not_found" }), { status: 404 })));
});
afterEach(() => vi.unstubAllGlobals());

test("страница качества показывает цифры отчёта make metrics", async () => {
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter>
        <Quality />
      </MemoryRouter>
    </Providers>,
  );
  expect(screen.getByRole("heading", { name: "Качество" })).toBeInTheDocument();
  for (const r of report.rows) expect(screen.getByTestId(`val-${r.id}`)).toHaveTextContent(r.value_text);
  expect(screen.getByTestId("sum-green")).toHaveTextContent(String(report.summary.green));
  expect(screen.getByTestId("sum-red")).toHaveTextContent(String(report.summary.red));
  expect(await screen.findByText(/Пока нет событий/)).toBeInTheDocument();
});

test("в отчёте нет метрик без готовой строки значения", () => {
  expect(report.rows.length).toBeGreaterThan(0);
  for (const r of report.rows) {
    expect(r.value_text).toBeTruthy();
    expect(r.target_text).toBeTruthy();
  }
});

function renderAt(ui: React.ReactElement) {
  return render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter>{ui}</MemoryRouter>
    </Providers>,
  );
}

test("страница справедливости показывает impact ratio из отчёта", () => {
  renderAt(<Fairness />);
  const row = report.rows.find((r) => r.id === "fairness");
  expect(row).toBeTruthy();
  expect(screen.getByTestId("fair-value")).toHaveTextContent(row!.value_text);
  expect(screen.getByTestId("fair-verdict")).toBeInTheDocument();
});

test("живые прогоны: сводка и список", async () => {
  const run = { id: "r1", scenario: "candidate", token: "t", path: "/run/t", status: "finished", invited_at: null, started_at: null, finished_at: null, tasks: [], tasks_done: 3, tasks_total: 4, steps: 9, total_time_s: 300, stuck_task: "Тест", sus_score: 72.5, category_agree: true, notes: null };
  const body = { items: [run], summary: { runs: 1, finished: 1, task_success_pct: 75, median_time_s: 300, median_sus: 72.5, category_agree_pct: 100 } };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } })));
  renderAt(<Runs />);
  expect(await screen.findByTestId("run-summary")).toHaveTextContent("75 %");
  expect(screen.getByText("3/4")).toBeInTheDocument();
  expect(screen.getByText("Тест")).toBeInTheDocument();
});

test("живые прогоны: пустой список", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items: [], summary: { runs: 0, finished: 0, task_success_pct: null, median_time_s: null, median_sus: null, category_agree_pct: null } }), { status: 200, headers: { "content-type": "application/json" } })));
  renderAt(<Runs />);
  expect(await screen.findByText(/Прогонов пока нет/)).toBeInTheDocument();
});

test("причина «не измерено» без команд разработчика", () => {
  expect(T.unavailable("load", "нет reports/load/load_stats.csv (нужен `make up`, `make seed`, `make load`)")).toBe("Не измерено — load: нет reports/load/load_stats.csv");
});

test("главные метрики: 4–6 карточек, у каждой смысл и методика", async () => {
  const { HEADLINES } = await import("./headline");
  expect(HEADLINES.length).toBeGreaterThanOrEqual(4);
  expect(HEADLINES.length).toBeLessThanOrEqual(6);
  renderAt(<Quality />);
  for (const h of HEADLINES) {
    const card = screen.getByTestId(`headline-${h.id}`);
    expect(card).toHaveTextContent(h.title);
    expect(card).toHaveTextContent(h.means);
    expect(h.method.length).toBeGreaterThan(20);
    expect(card.querySelector('[data-testid="headline-tip"]')).toBeTruthy();
  }
});

test("главные метрики: «не измерено» без данных онлайн-метрик", async () => {
  renderAt(<Quality />);
  await screen.findByText(/Пока нет событий/);
  expect(screen.getByTestId("headline-value-online")).toHaveTextContent("—");
  expect(screen.getByTestId("headline-online")).toHaveTextContent("Не измерено");
});

test("у каждого графика подписаны обе оси", () => {
  renderAt(<Quality />);
  const charts = screen.getAllByTestId("chart");
  expect(charts.length).toBeGreaterThan(0);
  for (const c of charts) {
    expect(c.querySelector('[data-testid="x-label"]')?.textContent).toBeTruthy();
    expect(c.querySelector('[data-testid="y-label"]')?.textContent).toBeTruthy();
  }
});
