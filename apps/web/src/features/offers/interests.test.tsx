import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

type Call = { method: string; url: string; body: Record<string, unknown> | null };
const calls: Call[] = [];
let role: "candidate" | "employer" = "candidate";
let routes: (url: string, method: string) => Response | null = () => null;

const company = { id: "c1", name: "Северный код", responsibility_score: 4.6, verified: true, reliability: { responsibility_score: 4.6, response_rate: 0.8, avg_response_hours: 6, sample: 12 } };
const interestOffer = (id: string, status: string, extra: Record<string, unknown> = {}) => ({
  id, status, created_at: "2026-10-02T10:00:00Z", expires_at: "2026-10-09T10:00:00Z",
  vacancy: { id: "v1", title: "Backend (Python)", role: "backend", grade_min: "middle", grade_max: "middle_plus", formats: ["remote"], employment_type: "full" },
  salary_from: 200000, salary_to: 260000, below_candidate_min: false, match_snapshot: null, decline: null, message: "Нам нужен ваш опыт с очередями",
  why_you: { factors: [{ code: "skills", text: "Подтверждены Python и PostgreSQL", weight: 0.9 }], unconfirmed: ["Нет подтверждения Docker"] },
  company, ...extra,
});
const card = {
  pseudo_id: "p1", pseudonym: "Backend #1", avatar_seed: "abc", primary_role: "backend", grade: "middle", grade_preliminary: false,
  primary_stack: ["python"], top_skills: [], fsp_highlights: [], salary_min: 230000, formats: ["remote"], city: null, relocation: false,
  search_status: "active", updated_at: "2026-10-02T00:00:00Z", skills: [], grade_info: { breakdown: [] }, experience: [], offers_from_you: [], interested_you: true,
};

beforeEach(() => {
  calls.length = 0;
  role = "candidate";
  routes = () => null;
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "u@b.ru", role, consents: ["pd_processing"] });
      if (method !== "GET") calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : null });
      return routes(url, method) ?? res(404);
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

test("кандидат: агрегат, «почему вы», рейтинг компании; «открыть» уходит в /interests/{id}/open", async () => {
  routes = (url, method) => {
    if (url.endsWith("/candidates/me/interests")) {
      return res(200, { companies: 2, salary_from_min: 200000, salary_to_max: 300000, items: [interestOffer("i1", "interest"), interestOffer("i2", "interest_opened", { company: { ...company, id: "c2", name: "Южный софт" } })] });
    }
    if (method === "POST" && url.endsWith("/interests/i1/open")) return res(200, interestOffer("i1", "interest_opened"));
    return null;
  };
  mount("/me/interests");
  expect(await screen.findByText(/2 компании интересуются вами/)).toBeInTheDocument();
  expect(screen.getByText(/Вилки компаний/)).toBeInTheDocument();
  expect(screen.getAllByText("Подтверждены Python и PostgreSQL")).toHaveLength(2);
  expect(screen.getAllByText("Нет подтверждения Docker")).toHaveLength(2);
  expect(screen.getAllByText(/отвечает на 80% обращений, в среднем за 6 ч/)).toHaveLength(2);
  expect(screen.getByText(/Вы открыли интерес/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Открыть интерес" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/interests/i1/open"))).toBe(true));
});

test("кандидат: «не интересно» — причина одним тапом в нижнем листе", async () => {
  routes = (url, method) => {
    if (url.endsWith("/candidates/me/interests")) return res(200, { companies: 1, salary_from_min: 200000, salary_to_max: 260000, items: [interestOffer("i1", "interest")] });
    if (method === "POST" && url.endsWith("/interests/i1/decline")) return res(200, interestOffer("i1", "declined"));
    return null;
  };
  mount("/me/interests");
  fireEvent.click(await screen.findByRole("button", { name: "Не интересно" }));
  fireEvent.click(await screen.findByRole("button", { name: /Не та компания/ }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body).toEqual({ reason: "wrong_company", comment: null });
});

test("кандидат: пустое состояние", async () => {
  routes = (url) => (url.endsWith("/candidates/me/interests") ? res(200, { companies: 0, salary_from_min: null, salary_to_max: null, items: [] }) : null);
  mount("/me/interests");
  expect(await screen.findByText("Пока никто не интересуется")).toBeInTheDocument();
});

test("на экране приглашений кандидата есть плашка «Вами интересуются»", async () => {
  routes = (url) => {
    if (url.endsWith("/candidates/me/interests")) return res(200, { companies: 3, salary_from_min: 1, salary_to_max: 2, items: [] });
    if (url.endsWith("/candidates/me/offers")) return res(200, []);
    return null;
  };
  mount("/me/offers");
  const link = await screen.findByRole("link", { name: /Вами интересуются: 3/ });
  expect(link).toHaveAttribute("href", "/me/interests");
});

const employerRoutes = (url: string, method: string): Response | null => {
  if (url.includes("/vacancies")) return res(200, [{ id: "v1", company_id: "c1", title: "Backend (Python)", role: "backend", grade_min: "middle", grade_max: "middle_plus", formats: ["remote"], employment_type: "full", city: null, salary_from: 200000, salary_to: 250000, range_too_wide: false, description: null, status: "published", important_qualities: [], skills: [], version: 1, created_at: "2026-10-01T00:00:00Z", published_at: "2026-10-01T00:00:00Z" }]);
  if (url.includes("/candidates/p1/card")) return res(200, card);
  if (url.includes("/offers/salary-hint")) {
    return res(200, { candidate_min: 230000, below_candidate_min: false, p_accept: 0.4, acceptance_hint: "medium", range_too_wide: false, message: "", suggested_salary_to: 280000, suggested_p_accept: 0.7, avg_response_hours: 30 });
  }
  if (method === "POST" && url.endsWith("/interests")) return res(201, { ...interestOffer("i9", "interest"), candidate: card });
  return null;
};

test("работодатель: модалка интереса с подсказкой «поднимите верх вилки», сообщение ≤ 300, POST /interests", async () => {
  role = "employer";
  routes = employerRoutes;
  mount("/employer/candidates/p1?vacancy=v1");
  expect(await screen.findByText("Вами интересовался")).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button", { name: "Проявить интерес" }));
  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText(/Поднимите верх вилки до 280\s000\s₽/)).toBeInTheDocument();
  expect(within(dialog).getByText(/в среднем за 1 дн\./)).toBeInTheDocument();
  const msg = within(dialog).getByLabelText(/Короткое сообщение/) as HTMLTextAreaElement;
  expect(msg.maxLength).toBe(300);
  fireEvent.click(within(dialog).getByRole("button", { name: "Применить" }));
  fireEvent.change(msg, { target: { value: "Здравствуйте" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Отметить «интересен»" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/interests"))).toBe(true));
  expect(calls.find((c) => c.url.endsWith("/interests"))?.body).toMatchObject({ candidate_pseudo_id: "p1", vacancy_id: "v1", salary_from: 200000, salary_to: 280000, message: "Здравствуйте" });
});

test("работодатель: приглашение по открытому интересу — вилка из интереса, POST /interests/{id}/invite", async () => {
  role = "employer";
  const opened = { ...interestOffer("i9", "interest_opened"), candidate: card };
  routes = (url, method) => {
    if (method === "POST" && url.endsWith("/interests/i9/invite")) return res(200, { ...opened, status: "sent" });
    if (/\/offers\/i9$/.test(url)) return res(200, opened);
    if (/\/offers\/i9\/(messages|events)/.test(url)) return res(200, []);
    return employerRoutes(url, method);
  };
  mount("/employer/offers/i9");
  expect(await screen.findByText(/Кандидат открыл интерес/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Пригласить" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(await within(dialog).findByRole("button", { name: "Отправить приглашение" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/interests/i9/invite"))).toBe(true));
  expect(calls.find((c) => c.url.endsWith("/interests/i9/invite"))?.body).toMatchObject({ salary_from: 200000, salary_to: 260000 });
});

test("подписки: создание с фильтром и удаление", async () => {
  role = "employer";
  const sub = { id: "s1", profession: "backend", grades: ["middle"], skills: [], salary_max: 300000, formats: ["remote"], only_confirmed: true, created_at: "2026-10-02T10:00:00Z" };
  routes = (url, method) => {
    if (url.endsWith("/subscriptions") && method === "GET") return res(200, [sub]);
    if (url.endsWith("/subscriptions") && method === "POST") return res(201, sub);
    if (url.endsWith("/subscriptions/s1") && method === "DELETE") return new Response(null, { status: 204 });
    if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "python", name: "Python" }] });
    return null;
  };
  mount("/employer/subscriptions?profession=backend&grade=middle");
  expect(await screen.findByText(/бюджет до/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Бюджет до/), { target: { value: "300000" } });
  fireEvent.click(screen.getByLabelText("Удалённо"));
  fireEvent.click(screen.getByLabelText(/Только подтверждённые/));
  fireEvent.click(screen.getByRole("button", { name: "Подписаться" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST")).toBe(true));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ profession: "backend", grades: ["middle"], skills: [], salary_max: 300000, formats: ["remote"], only_confirmed: true });
  fireEvent.click(screen.getByRole("button", { name: /Удалить подписку/ }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
});
