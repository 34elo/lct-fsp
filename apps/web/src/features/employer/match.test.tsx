import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const middle = { profession: "backend", title: "Backend", grade: "middle", affinity: 0.82, candidates: 5, median_salary: 220000, fsp_share: 0.24 };
const junior = { profession: "backend", title: "Backend", grade: "junior", affinity: 0.7, candidates: 2, median_salary: 120000, fsp_share: 0.23 };
const need = {
  id: "n1", text: "Backend на Python, Middle", filters: { roles: ["backend"], formats: ["remote"], salary_max: 220000 }, skills: { python: 1 },
  grades: ["middle"], shortlist: [], created_at: "2026-10-05T00:00:00Z", categories: [middle, junior],
};
const base = {
  avatar_seed: "x", primary_role: "backend", grade: "middle", grade_preliminary: false, primary_stack: ["python"],
  top_skills: [{ slug: "python", name: "Python", level: 3, sources: ["test"] }], fsp_highlights: [], salary_min: 200000,
  formats: ["remote"], city: null, relocation: false, search_status: "active", updated_at: "2026-10-02T00:00:00Z",
  categories: [{ profession: "backend", grade: "middle" }],
};
const cards = [1, 2, 3, 4, 5].map((i) => ({ ...base, pseudo_id: `p${i}`, pseudonym: `Backend #${i}00${i}`, match: { score: 1 - i / 20, explanation: [] } }));
const activity = {
  items: [
    { id: "e1", kind: "interest_opened", at: new Date().toISOString(), candidate: { pseudo_id: "p1", pseudonym: "Backend #1001" }, link: "/employer/offers/o1" },
    { id: "e2", kind: "subscription_hit", at: "2026-10-06T09:00:00Z", candidate: { pseudo_id: "p2", pseudonym: "Backend #2002" }, link: "/employer/candidates/p2", detail: "Backend" },
  ],
};
const subs = [{ id: "s1", profession: "backend", grades: ["junior"], skills: [], salary_max: null, formats: [], only_confirmed: true, created_at: "2026-10-01T00:00:00Z" }];

const calls: { method: string; url: string; body?: unknown }[] = [];
let createStatus = 201;
let activityStatus = 200;
let categories = [middle, junior];

beforeEach(() => {
  calls.length = 0;
  createStatus = 201;
  activityStatus = 200;
  categories = [middle, junior];
  localStorage.clear();
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.endsWith("/needs") && method === "POST") return createStatus === 201 ? res(201, need) : res(422, { type: "x", title: "x", status: 422, code: "need_empty" });
      if (url.includes("/needs/n1/categories")) return res(200, { need_id: "n1", shortlist: [], categories });
      if (url.includes("/needs/gone/categories")) return res(404, { type: "x", title: "x", status: 404, code: "need_not_found" });
      if (url.includes("/categories/backend/middle/candidates")) return res(200, { items: cards, next_cursor: null, total: 5, session_id: "s1" });
      if (url.includes("/categories/backend/junior/candidates")) return res(200, { items: cards.slice(0, 2), next_cursor: null, total: 2, session_id: "s2" });
      if (url.includes("/employer/activity")) return activityStatus === 200 ? res(200, activity) : res(500, { type: "x", title: "x", status: 500, code: "internal" });
      if (url.endsWith("/subscriptions")) return res(200, subs);
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

test("первый вход: строка запроса, примеры и лента; Подбор в меню, Поиска нет", async () => {
  mount("/employer");
  expect(await screen.findByRole("textbox", { name: "Кого вы ищете" })).toHaveValue("");
  const examples = await screen.findByTestId("match-examples");
  expect(within(examples).getAllByRole("button")).toHaveLength(3);
  const feed = await screen.findByTestId("match-feed");
  expect(await within(feed).findByRole("link", { name: "Backend #1001" })).toHaveAttribute("href", "/employer/offers/o1");
  expect(within(feed).getByText(/открыл ваш интерес/)).toBeInTheDocument();
  expect(within(feed).getByText("сегодня")).toBeInTheDocument();
  expect(within(feed).getByText(/подошёл по подписке Backend/)).toBeInTheDocument();
  const nav = screen.getAllByRole("navigation", { name: "Разделы" })[0]!;
  expect(within(nav).getByRole("link", { name: "Подбор" })).toHaveAttribute("aria-current", "page");
  expect(within(nav).queryByRole("link", { name: "Поиск" })).not.toBeInTheDocument();
});

test("запрос → категории, чипсы, топ-3 и «Ещё», подписки; выбор категории меняет совпадения", async () => {
  mount("/employer");
  fireEvent.change(await screen.findByRole("textbox", { name: "Кого вы ищете" }), { target: { value: "Backend на Python, Middle" } });
  fireEvent.click(screen.getByRole("button", { name: "Подобрать" }));

  expect(await screen.findByText("5 человек")).toBeInTheDocument();
  const top = await screen.findByTestId("match-top");
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "Backend на Python, Middle" });
  expect(within(top).getAllByRole("article")).toHaveLength(3);
  expect(within(top).getAllByRole("link", { name: "Открыть профиль" })[0]).toHaveAttribute("href", "/employer/candidates/p1?source=match");
  expect(within(screen.getByTestId("match-chips")).getByText("Backend")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Кого вы ищете" })).toHaveValue("Backend на Python, Middle");

  const more = screen.getByTestId("match-more");
  expect(within(more).getByRole("link", { name: "Ещё 2" })).toHaveAttribute("href", "/employer/categories/backend/middle?need_id=n1");
  expect(within(more).getAllByRole("link", { name: /Backend #/ })).toHaveLength(2);

  const subsPanel = await screen.findByTestId("match-subscriptions");
  expect(within(subsPanel).getByText("Backend · Junior")).toBeInTheDocument();

  const catsPanel = screen.getByTestId("match-categories");
  expect(within(catsPanel).getByRole("button", { name: /Backend · Middle/ })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(within(catsPanel).getByRole("button", { name: /Backend · Junior/ }));
  expect(await screen.findByText("2 человека")).toBeInTheDocument();
  expect(within(await screen.findByTestId("match-top")).getAllByRole("article")).toHaveLength(2);
  expect(screen.queryByTestId("match-more")).not.toBeInTheDocument();
});

test("повторный вход: категории последнего запроса и топ-3 без «Ещё»", async () => {
  localStorage.setItem("fsp.employer.lastNeed", JSON.stringify({ id: "n1", text: "Backend", chips: ["Backend"] }));
  mount("/employer");
  expect(await screen.findByTestId("match-categories")).toBeInTheDocument();
  expect(await screen.findByText("топ-3")).toBeInTheDocument();
  expect(within(await screen.findByTestId("match-top")).getAllByRole("article")).toHaveLength(3);
  expect(screen.queryByTestId("match-more")).not.toBeInTheDocument();
  expect(screen.queryByTestId("match-subscriptions")).not.toBeInTheDocument();
});

test("запомненный запрос пропал — снова примеры", async () => {
  localStorage.setItem("fsp.employer.lastNeed", JSON.stringify({ id: "gone", text: "x", chips: [] }));
  mount("/employer");
  expect(await screen.findByTestId("match-examples")).toBeInTheDocument();
  expect(localStorage.getItem("fsp.employer.lastNeed")).toBeNull();
});

test("непонятный запрос — ошибка строкой", async () => {
  createStatus = 422;
  mount("/employer");
  fireEvent.click(await screen.findByRole("button", { name: "Backend на Python, Middle, до 220 тыс., удалёнка" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Не поняли запрос");
});

test("никого нет — ближайшие категории и подписка", async () => {
  categories = [{ ...middle, candidates: 0 }];
  mount("/employer?need=n1");
  expect(await screen.findByText("В ближайших категориях пока никого нет")).toBeInTheDocument();
  expect(screen.getByTestId("match-categories")).toBeInTheDocument();
});

test("категорий нет — пустое состояние; лента с ошибкой — «Повторить»", async () => {
  categories = [];
  activityStatus = 500;
  mount("/employer?need=n1");
  expect(await screen.findByText("Под запрос никого нет")).toBeInTheDocument();
  const feed = screen.getByTestId("match-feed");
  // Запрос ленты повторяется клиентом перед ошибкой — ждём дольше обычного.
  expect(await within(feed).findByRole("button", { name: "Повторить" }, { timeout: 5000 })).toBeInTheDocument();
});
