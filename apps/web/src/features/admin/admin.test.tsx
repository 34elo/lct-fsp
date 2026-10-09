import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import { NAV, ROUTES } from "@/app/routes";
import Dashboard from "@/features/admin/Dashboard";
import Home from "@/features/admin/Home";
import { WHY } from "@/features/admin/text";
import Moderation from "@/features/admin/Moderation";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];
let companies: { id: string; name: string; status: string; inn: string | null }[];
let summary: { status: number; body?: unknown };
const queues = (fsp: number | null, rest = 0) => ({
  queues: [
    { id: "fsp_requests", count: fsp },
    { id: "families", count: rest },
    { id: "skills", count: 0 },
    { id: "companies", count: rest },
    { id: "complaints", count: 0 },
  ],
  total: (fsp ?? 0) + 2 * rest,
});

const dashboard = {
  since: "2026-09-06T00:00:00Z",
  days: 30,
  min_cell: 5,
  funnel: [
    { id: "registered", title: "Регистрация", count: 120, hidden: false, pct_of_registered: 100, pct_of_previous: null },
    { id: "tested", title: "Тест", count: 60, hidden: false, pct_of_registered: 50, pct_of_previous: 50 },
    { id: "category", title: "Категория", count: null, hidden: true, pct_of_registered: null, pct_of_previous: null },
    { id: "invited", title: "Приглашение", count: null, hidden: true, pct_of_registered: null, pct_of_previous: null },
  ],
  fsp_share: { count: 30, hidden: false, pct: 25, of: 120 },
  navigator_to_competition: { count: null, hidden: true, pct: null, of: null },
};

beforeEach(() => {
  calls.length = 0;
  companies = [{ id: "c1", name: "Вымышленная Компания", status: "pending", inn: "7700000000" }];
  summary = { status: 200, body: queues(3, 2) };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.includes("/admin/dashboard")) return res(200, dashboard);
      if (url.includes("/admin/summary")) return res(summary.status, summary.body);
      if (url.includes("/admin/companies/c1/verify")) {
        companies[0].status = "verified";
        return res(200, companies[0]);
      }
      if (url.includes("/admin/companies")) return res(200, companies);
      if (url.includes("/admin/complaints/k1/resolve")) return res(200, {});
      if (url.includes("/admin/complaints"))
        return res(200, [{ id: "k1", offer_id: "12345678-aaaa", company_id: "c1", company_name: "Вымышленная Компания", reason: "spam", comment: "Дубли", status: "open", created_at: "2026-10-01T00:00:00Z" }]);
      return res(404, { code: "not_found" });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const mount = (ui: React.ReactElement, path = "/federation") =>
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
    </Providers>,
  );

test("главная: счётчики «Что требует вас» из API ведут в очереди", async () => {
  mount(<Home />);
  const fsp = await screen.findByTestId("queue-fsp_requests");
  expect(fsp).toHaveTextContent("3");
  expect(fsp).toHaveAttribute("href", "/federation/requests");
  expect(screen.getByTestId("queue-families")).toHaveAttribute("href", "/admin/families");
  expect(screen.getByTestId("queue-complaints")).toHaveAttribute("href", "/federation/moderation?tab=complaints");
  expect(screen.getByTestId("queue-companies")).toHaveTextContent("2");
  expect(screen.queryByTestId("admin-clear")).toBeNull();
  // что работает само — текстом, без действий
  expect(screen.getByTestId("admin-auto")).toHaveTextContent("Калибровка");
  expect(screen.getByText("Модерируется только это — остальное платформа делает автоматически.")).toBeInTheDocument();
  // каждая ссылка главной ведёт на экран из карты маршрутов
  const paths = new Set(ROUTES.map((r) => r.path));
  for (const a of screen.getAllByRole("link")) expect(paths.has(a.getAttribute("href")!.split("?")[0]), a.getAttribute("href")!).toBe(true);
});

test("главная: всё разобрано — спокойное сообщение; ФСП недоступен — «нет связи»", async () => {
  summary = { status: 200, body: queues(0) };
  const { unmount } = mount(<Home />);
  expect(await screen.findByTestId("admin-clear")).toBeInTheDocument();
  unmount();
  summary = { status: 200, body: queues(null) };
  mount(<Home />);
  expect(await screen.findByTestId("queue-fsp_requests")).toHaveTextContent("нет связи");
  expect(screen.queryByTestId("admin-clear")).toBeNull();
});

test("главная: ошибка сводки — повторить", async () => {
  summary = { status: 500, body: { code: "boom" } };
  mount(<Home />);
  expect(await screen.findByRole("button", { name: "Повторить" })).toBeInTheDocument();
});

test("у каждой страницы админки есть подзаголовок «зачем» (E39-29)", () => {
  const admin = ROUTES.filter((r) => r.section === "admin" && !r.redirect);
  for (const r of admin) expect(WHY[r.path], r.path).toBeTruthy();
  for (const n of NAV.admin) expect(WHY[n.to], n.to).toBeTruthy();
});

test("модерация: ?tab=complaints открывает жалобы", async () => {
  mount(<Moderation />, "/federation/moderation?tab=complaints");
  expect(await screen.findByText("Дубли")).toBeInTheDocument();
  expect(screen.getByTestId("page-why")).toHaveTextContent("Компании проходят проверку");
});

test("дашборд: скрытые ячейки показываются как «< 5»", async () => {
  mount(<Dashboard />);
  expect(await screen.findByTestId("stage-registered")).toHaveTextContent("120");
  expect(screen.getByTestId("stage-category")).toHaveTextContent("< 5");
  expect(screen.getByTestId("stage-invited")).toHaveTextContent("< 5");
  const ratios = screen.getAllByTestId("ratio-value");
  expect(ratios[0]).toHaveTextContent("30 из 120 (25%)");
  expect(ratios[1]).toHaveTextContent("< 5");
});

test("дашборд: смена периода перезапрашивает с days", async () => {
  mount(<Dashboard />);
  await screen.findByTestId("stage-registered");
  fireEvent.click(screen.getByRole("button", { name: "За 7 дн." }));
  await waitFor(() => expect(calls.some((c) => c.url.includes("days=7"))).toBe(true));
});

test("модерация: подтверждение компании", async () => {
  mount(<Moderation />);
  expect(await screen.findByText("Вымышленная Компания")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.includes("/admin/companies/c1/verify"))).toBe(true));
});

test("модерация: разбор жалобы отправляет решение", async () => {
  mount(<Moderation />);
  fireEvent.click(await screen.findByRole("tab", { name: "Жалобы" }));
  expect(await screen.findByText("Дубли")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Отклонить жалобу" }));
  await waitFor(() => {
    const c = calls.find((x) => x.method === "POST" && x.url.includes("/admin/complaints/k1/resolve"));
    expect(c?.body).toEqual({ decision: "dismissed" });
  });
});
