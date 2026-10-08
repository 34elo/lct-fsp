import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const category = { profession: "backend", title: "Backend", grade: "middle", affinity: 0.82, candidates: 12, median_salary: 210000, fsp_share: 0.34 };
const fewCategory = { profession: "devops", title: "DevOps", grade: "middle", affinity: 0.47, candidates: 2, median_salary: null, fsp_share: null };
const need = {
  id: "n1", text: "бэкенд на Python", filters: { roles: ["backend"], formats: ["remote"], salary_max: 220000 }, skills: { python: 1 },
  grades: ["middle"], shortlist: [], created_at: "2026-10-05T00:00:00Z", categories: [category, fewCategory],
};
const base = {
  avatar_seed: "x", primary_role: "backend", grade_preliminary: false, primary_stack: ["python"],
  top_skills: [{ slug: "python", name: "Python", level: 3, sources: ["fsp"] }], fsp_highlights: [], salary_min: 200000,
  formats: ["remote"], city: null, relocation: false, search_status: "active", updated_at: "2026-10-02T00:00:00Z",
};
const cards = [
  { ...base, pseudo_id: "p1", pseudonym: "Backend #4821", grade: "middle", categories: [{ profession: "backend", grade: "middle" }], strength: { value: 0.74, rank: 0.88, top: [{ code: "T", text: "Тест пройден уверенно", value: 0.9, weight: 0.4 }] }, match: { score: 0.92, explanation: [] }, is_shortlisted: false },
  { ...base, pseudo_id: "p2", pseudonym: "Backend #3077", grade: "senior", categories: [{ profession: "backend", grade: "middle" }], strength: { value: 0.66, rank: 0.81 }, match: { score: 0.88, explanation: [] }, is_shortlisted: true },
  { ...base, pseudo_id: "p3", pseudonym: "Backend #5502", grade: "middle", formats: ["office"], categories: [], strength: null, match: { score: 0.74, explanation: [] }, is_shortlisted: false },
];
const calls: { method: string; url: string; body?: unknown }[] = [];
let createStatus = 201;
let tuned = false;

beforeEach(() => {
  calls.length = 0;
  createStatus = 201;
  tuned = false;
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
      if (url.includes("/needs/n1/categories")) return res(200, { need_id: "n1", shortlist: [], categories: [category, fewCategory] });
      if (url.includes("/needs/n1/shortlist/")) return res(method === "DELETE" ? 204 : 204);
      if (url.includes("/categories/backend/middle/candidates")) return res(200, { items: cards, next_cursor: null, total: 3, session_id: "s1" });
      if (url.endsWith("/recs/feedback")) {
        const chips = tuned ? [{ feature: "fsp", text: "чаще выбираете кандидатов с подтверждением ФСП ×1.3", change: 0.3 }] : [];
        return res(200, { id: 1, impression_id: 1, event: "dismiss", created_at: "2026-10-06T00:00:00Z", tuning: { session_id: "s1", active: tuned, signals: 3, min_signals: 3, weights: [], chips, hints: [] } });
      }
      if (url.endsWith("/recs/sessions/s1") && method === "DELETE") return res(204);
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

test("потребность текстом ведёт к категориям с чипсами и счётчиками", async () => {
  mount("/employer/needs/new");
  fireEvent.change(await screen.findByRole("textbox", { name: "Кого ищете" }), { target: { value: "бэкенд на Python, удалёнка, до 220 000" } });
  fireEvent.click(screen.getByRole("button", { name: "Показать категории" }));
  const list = await screen.findByRole("list", { name: "Рекомендованные категории" });
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "бэкенд на Python, удалёнка, до 220 000" });
  const best = within(list).getByRole("article", { name: "Backend, Middle" });
  expect(within(best).getByText("Лучшее совпадение")).toBeInTheDocument();
  expect(within(best).getByText("0.82")).toBeInTheDocument();
  expect(within(best).getByText("210 000 ₽")).toBeInTheDocument();
  expect(within(best).getByText("34%")).toBeInTheDocument();
  expect(within(best).getByRole("link", { name: "Смотреть кандидатов (12)" })).toHaveAttribute("href", "/employer/categories/backend/middle?need_id=n1");
  expect(within(list).getByText(/Мало кандидатов/)).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Поняли так" })).toHaveTextContent("python");
});

test("пустая потребность (422 need_empty) предлагает форму", async () => {
  createStatus = 422;
  mount("/employer/needs/new");
  fireEvent.change(await screen.findByRole("textbox", { name: "Кого ищете" }), { target: { value: "ну такое" } });
  fireEvent.click(screen.getByRole("button", { name: "Показать категории" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось разобрать текст");
  expect(screen.getByRole("link", { name: "Открыть форму" })).toHaveAttribute("href", "/employer/search");
});

test("кандидаты категории: подтверждённые по рангу, неподтверждённые ниже, шорт-лист, фильтр не сбрасывает отмеченных", async () => {
  mount("/employer/categories/backend/middle?need_id=n1");
  const first = await screen.findByRole("article", { name: "Backend #4821" });
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Backend · Middle");
  expect(screen.getByTestId("category-stats")).toHaveTextContent("3 человек");
  // пустые параметры не уходят строкой «null» (бэкенд отвечал 422)
  const req = calls.find((c) => c.url.includes("/categories/backend/middle/candidates"));
  expect(req?.url).toContain("need_id=n1");
  expect(req?.url).not.toContain("null");
  expect(within(first).getByText("подтверждён")).toBeInTheDocument();
  expect(within(first).getByText("сила 74 · ранг 0.88")).toBeInTheDocument();
  // p3 без теста — в группе «Не подтверждены», с меткой и пунктиром
  const third = screen.getByRole("article", { name: "Backend #5502" });
  expect(third).toHaveAttribute("data-confirmed", "false");
  expect(within(third).getByText("не подтверждён")).toBeInTheDocument();
  expect(within(third).getByText("Навыки не подтверждены тестом")).toBeInTheDocument();
  const group = screen.getByRole("region", { name: "Не подтверждены" });
  expect(within(group).getByRole("article", { name: "Backend #5502" })).toBeInTheDocument();
  expect(within(screen.getByRole("article", { name: "Backend #3077" })).getByText("Заявленный грейд выше подтверждённого")).toBeInTheDocument();

  // отметка в шорт-лист уходит на сервер
  fireEvent.click(within(first).getByRole("button", { name: "В шорт-лист" }));
  await vi.waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/needs/n1/shortlist/p1"))).toBe(true));
  expect(within(first).getByRole("button", { name: /В шорт-листе/ })).toHaveAttribute("aria-pressed", "true");

  // фильтр «только подтверждённые»: p3 уходит, p1 и p2 (в шорт-листе) остаются
  fireEvent.click(screen.getByRole("button", { name: /Только подтверждённые/ }));
  expect(screen.queryByRole("article", { name: "Backend #5502" })).toBeNull();
  expect(screen.getByRole("article", { name: "Backend #3077" })).toBeInTheDocument();
  // снятие отметки уходит DELETE-ом
  fireEvent.click(within(screen.getByRole("article", { name: "Backend #3077" })).getByRole("button", { name: /В шорт-листе/ }));
  await vi.waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/needs/n1/shortlist/p2"))).toBe(true));
});

test("фильтры категории: стек и «ФСП» дают пустое состояние со сбросом", async () => {
  mount("/employer/categories/backend/middle?need_id=n1");
  await screen.findByRole("article", { name: "Backend #4821" });
  fireEvent.change(screen.getByRole("combobox", { name: "Стек" }), { target: { value: "Python" } });
  expect(screen.getAllByRole("article")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: /ФСП/ }));
  // в шорт-листе остаётся p2; снимаем отметку — и по фильтру никого
  fireEvent.click(within(screen.getByRole("article", { name: "Backend #3077" })).getByRole("button", { name: /В шорт-листе/ }));
  expect(await screen.findByText("В категории никого по фильтрам")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
  expect(await screen.findByRole("article", { name: "Backend #4821" })).toBeInTheDocument();
});

test("«не подходит» скрывает карточку, «Интерес» открывает модалку на месте", async () => {
  mount("/employer/categories/backend/middle?need_id=n1");
  const first = await screen.findByRole("article", { name: "Backend #4821" });
  fireEvent.click(within(screen.getByRole("article", { name: "Backend #3077" })).getByRole("button", { name: "Не подходит" }));
  expect(screen.queryByRole("article", { name: "Backend #3077" })).toBeNull();
  fireEvent.click(within(first).getByRole("button", { name: "Интерес" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText("Интерес · Backend #4821")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Отправить" })).toBeDisabled();
});

test("реакции уходят в /recs/feedback, чипсы «Учли» появляются и сбрасываются", async () => {
  mount("/employer/categories/backend/middle?need_id=n1");
  const first = await screen.findByRole("article", { name: "Backend #4821" });
  tuned = true;
  fireEvent.click(within(first).getByRole("button", { name: "В шорт-лист" }));
  await vi.waitFor(() =>
    expect(calls.find((c) => c.url.endsWith("/recs/feedback"))?.body).toEqual({ session_id: "s1", candidate_pseudo_id: "p1", event: "shortlist" }),
  );
  fireEvent.click(within(screen.getByRole("article", { name: "Backend #3077" })).getByRole("button", { name: "Не подходит" }));
  await vi.waitFor(() => expect(calls.filter((c) => c.url.endsWith("/recs/feedback")).map((c) => (c.body as { event: string }).event)).toEqual(["shortlist", "dismiss"]));
  const chips = await screen.findByRole("list", { name: "Учли" });
  expect(chips).toHaveTextContent("Учли: чаще выбираете кандидатов с подтверждением ФСП");
  fireEvent.click(within(chips).getByRole("button", { name: "Сбросить подстройку" }));
  await vi.waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/recs/sessions/s1"))).toBe(true));
  expect(screen.queryByRole("list", { name: "Учли" })).toBeNull();
});
