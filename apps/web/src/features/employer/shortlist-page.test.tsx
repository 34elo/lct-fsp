import { fireEvent, render, screen, within } from "@testing-library/react";
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
let offers: unknown[] = [];
let catsStatus = 200;

beforeEach(() => {
  shortlist = ["p1", "p2"];
  offers = [offer("o2", "interest", card("p2", "Backend #4821"))];
  catsStatus = 200;
  localStorage.clear();
  localStorage.setItem("fsp.employer.lastNeed", JSON.stringify({ id: "n1", text: "x", chips: [] }));
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      if (url.includes("/needs/n1/categories")) return catsStatus === 200 ? res(200, { need_id: "n1", shortlist, categories: [] }) : res(503, { type: "x", title: "x", status: 503, code: "down" });
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
  catsStatus = 503;
  mount();
  expect(await screen.findByText("ошибка 503")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
});

test("без запроса в браузере: пустой шорт-лист", async () => {
  localStorage.clear();
  mount();
  expect(await screen.findByText("Шорт-лист пуст")).toBeInTheDocument();
});
