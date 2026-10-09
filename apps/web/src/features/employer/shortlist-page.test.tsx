import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const card = (id: string, name: string, extra: object = {}) => ({
  pseudo_id: id, pseudonym: name, avatar_seed: "x", primary_role: "backend", grade: "middle", grade_preliminary: false, primary_stack: ["python"],
  top_skills: [{ slug: "python", name: "Python", level: 3, sources: ["test"] }], fsp_highlights: [], salary_min: 190000, formats: ["remote"], city: null,
  relocation: false, search_status: "active", updated_at: "2026-10-02T00:00:00Z", categories: [{ profession: "backend", grade: "middle" }],
  skills: [], grade_info: {}, experience: [], offers_from_you: [], ...extra,
});
const offer = (id: string, status: string, c: ReturnType<typeof card>) => ({
  id, status, created_at: "2026-10-05T00:00:00Z", expires_at: "2026-10-12T00:00:00Z", salary_from: 190000, salary_to: 220000, below_candidate_min: false, candidate: c,
});

let shortlist: string[] = ["p1", "p2"];
let listStatus = 200;
let removed: string[] = [];
let offers: unknown[] = [];

beforeEach(() => {
  shortlist = ["p1", "p2"];
  offers = [offer("o2", "interest", card("p2", "Backend #4821"))];
  listStatus = 200;
  removed = [];
  localStorage.clear();
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      if (init?.method === "DELETE" && url.includes("/needs/n1/shortlist/")) {
        const id = url.split("/").pop()!;
        removed.push(id);
        shortlist = shortlist.filter((x) => x !== id);
        return res(204);
      }
      if (url.endsWith("/shortlist")) {
        return listStatus === 200 ? res(200, { items: shortlist.map((p) => ({ pseudo_id: p, need_id: "n1" })) }) : res(503, { type: "x", title: "x", status: 503, code: "down" });
      }
      if (url.includes("/candidates/p1/card")) return res(200, card("p1", "Backend #3377"));
      if (url.includes("/candidates/p2/card")) return res(200, card("p2", "Backend #4821"));
      if (url.includes("/offers")) return res(200, offers);
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(path = "/employer/shortlist") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

test("строки шорт-листа со статусом интереса; пункт меню активен", async () => {
  mount();
  const rows = await screen.findAllByTestId("shortlist-row");
  expect(rows).toHaveLength(2);
  expect(within(rows[0]!).getByText("интерес не отправлен")).toBeInTheDocument();
  expect(within(rows[0]!).getByRole("button", { name: "Интерес" })).toBeInTheDocument();
  expect(within(rows[1]!).getByText("ожидает ответа")).toBeInTheDocument();
  expect(within(rows[1]!).getByRole("link", { name: "Открыть" })).toHaveAttribute("href", "/employer/offers/o2");
  const nav = screen.getAllByRole("navigation", { name: "Разделы" })[0]!;
  expect(within(nav).getByRole("link", { name: "Шорт-лист" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("button", { name: "Пригласить" })).toBeInTheDocument();
});

test("«Интерес» открывает модалку на месте", async () => {
  mount();
  const rows = await screen.findAllByTestId("shortlist-row");
  fireEvent.click(within(rows[0]!).getByRole("button", { name: "Интерес" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
});

test("пусто: заголовок и переход к подбору", async () => {
  shortlist = [];
  mount();
  expect(await screen.findByText("Шорт-лист пуст")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Перейти к подбору" })).toHaveAttribute("href", "/employer");
});

test("ошибка: код и «Повторить»", async () => {
  listStatus = 503;
  mount();
  expect(await screen.findByText("ошибка 503")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
});

test("пустое состояние объясняет, зачем шорт-лист", async () => {
  shortlist = [];
  mount();
  expect(await screen.findByText(/Сохраняйте кандидатов из категорий, чтобы сравнить и пригласить/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Что такое «Шорт-лист»" })).toBeInTheDocument();
});

test("список не зависит от запроса, сохранённого в браузере", async () => {
  localStorage.clear();
  mount();
  expect(await screen.findAllByTestId("shortlist-row")).toHaveLength(2);
});

test("сравнение: нужно двое, показывает признаки рядом", async () => {
  mount();
  const rows = await screen.findAllByTestId("shortlist-row");
  const cmp = screen.getByRole("button", { name: /Сравнить/ });
  expect(cmp).toBeDisabled();
  fireEvent.click(within(rows[0]!).getByTestId("shortlist-pick"));
  expect(cmp).toBeDisabled();
  fireEvent.click(within(rows[1]!).getByTestId("shortlist-pick"));
  expect(screen.getByRole("button", { name: "Сравнить (2)" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "Сравнить (2)" }));
  const table = await screen.findByRole("table", { name: "Сравнение кандидатов рядом" });
  expect(within(table).getByText("Вилка от")).toBeInTheDocument();
  expect(within(table).getAllByText(/Python/)).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Закрыть сравнение" }));
  expect(screen.queryByTestId("shortlist-compare")).not.toBeInTheDocument();
});

test("убрать кандидата из шорт-листа", async () => {
  mount();
  const rows = await screen.findAllByTestId("shortlist-row");
  fireEvent.click(within(rows[0]!).getByRole("button", { name: "Убрать" }));
  await waitFor(() => expect(removed).toEqual(["p1"]));
  await waitFor(() => expect(screen.getAllByTestId("shortlist-row")).toHaveLength(1));
});
