import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { ApiError } from "@/api/mutator";
import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { offerErrorText } from "./text";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const vac = {
  id: "v1", company_id: "c1", title: "Backend (Python)", role: "backend", grade_min: "middle", grade_max: "middle_plus",
  formats: ["remote"], employment_type: "full", city: null, salary_from: 200000, salary_to: 280000, range_too_wide: false,
  description: null, status: "published", important_qualities: [], skills: [], version: 1,
  created_at: "2026-10-01T00:00:00Z", published_at: "2026-10-01T00:00:00Z",
};
const card = {
  pseudo_id: "p1", pseudonym: "Candidate #1", avatar_seed: "abc", primary_role: "backend", grade: "middle", grade_preliminary: false,
  primary_stack: ["python"], top_skills: [], fsp_highlights: [], salary_min: 300000, formats: ["remote"], city: null, relocation: false,
  search_status: "active", updated_at: "2026-10-02T00:00:00Z", skills: [], grade_info: { breakdown: [] }, experience: [], offers_from_you: [],
};
const calls: { url: string; headers: Headers; body: unknown }[] = [];

beforeEach(() => {
  calls.length = 0;
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      if (url.includes("/vacancies")) return res(200, [vac]);
      if (url.includes("/candidates/p1/card")) return res(200, card);
      if (url.includes("/offers/salary-hint")) {
        return res(200, { candidate_min: 300000, below_candidate_min: true, p_accept: 0.3, acceptance_hint: "low", range_too_wide: true, message: "" });
      }
      if (url.endsWith("/offers") && init?.method === "POST") {
        calls.push({ url, headers: new Headers(init.headers), body: JSON.parse(String(init.body)) });
        return res(429, { code: "offer_limit_exceeded", status: 429 });
      }
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

test("тексты ошибок приглашения по code", () => {
  expect(offerErrorText(new ApiError(429, "offer_limit_exceeded", {}))).toMatch(/Лимит приглашений/);
  expect(offerErrorText(new ApiError(409, "offer_exists", {}))).toMatch(/уже отправлен/);
  expect(offerErrorText(new ApiError(422, "salary_range_required", {}))).toMatch(/вилку/);
  expect(offerErrorText(new ApiError(429, undefined, {}))).toMatch(/Слишком много/);
});

test("форма приглашения: подсказка p_accept и предупреждения, ключ идемпотентности, текст ошибки 429", async () => {
  mount("/employer/offers/new?candidate=p1&vacancy=v1");
  expect(await screen.findByText(/Вероятность принятия: низкая/)).toBeInTheDocument();
  expect(screen.getByText(/ниже ожиданий кандидата/i)).toBeInTheDocument();
  expect(screen.getByText(/Слишком широкая вилка/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Отправить приглашение" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/Лимит приглашений на сутки/);
  expect(calls[0].headers.get("Idempotency-Key")).toMatch(/.{8,}/);
  expect(calls[0].body).toMatchObject({ vacancy_id: "v1", candidate_pseudo_id: "p1", salary_from: 200000, salary_to: 280000 });
});

test("пустая вилка не отправляется", async () => {
  mount("/employer/offers/new?candidate=p1&vacancy=v1");
  await screen.findByText(/Вероятность принятия/);
  const [from] = screen.getAllByRole("textbox", { name: /от/ });
  fireEvent.change(from, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить приглашение" }));
  await waitFor(() => expect(screen.getAllByText(/Укажите обе границы вилки/).length).toBeGreaterThan(0));
  expect(calls).toHaveLength(0);
});

const mkOffer = (id: string, status: string, extra: Record<string, unknown> = {}) => ({
  id, status, created_at: "2026-10-02T10:00:00Z", expires_at: "2026-10-16T10:00:00Z",
  vacancy: { id: "v1", title: "Backend (Python)", role: "backend", formats: ["remote"] },
  salary_from: 200000, salary_to: 250000, below_candidate_min: false,
  candidate: { ...card, pseudonym: `Backend #${id}` }, ...extra,
});

test("канбан E5: семь колонок, счётчики равны карточкам, причины отказов", async () => {
  const list = [
    mkOffer("1", "sent"), mkOffer("2", "sent"), mkOffer("3", "viewed"),
    mkOffer("4", "declined", { decline: { reason: "wrong_stack" } }), mkOffer("5", "expired"), mkOffer("6", "interest_opened"),
  ];
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => (url.endsWith("/offers") && init?.method !== "POST" ? res(200, list) : base(url, init)));
  mount("/employer/offers");
  const sent = await screen.findByRole("region", { name: "Отправлен" });
  expect(sent.querySelectorAll("li")).toHaveLength(2);
  expect(screen.getByRole("region", { name: "Нанят" })).toHaveTextContent("Пока пусто");
  expect(screen.getByRole("region", { name: "Закрыто" }).querySelectorAll("li")).toHaveLength(2);
  expect(screen.getAllByLabelText("Карточек: 2", { selector: "span" })).toHaveLength(2);
  expect(screen.getByRole("region", { name: "Интерес" }).querySelectorAll("li")).toHaveLength(1);
  const tabs = screen.getAllByRole("tab");
  expect(tabs).toHaveLength(7);
  expect(tabs[1]).toHaveTextContent("Отправлен2");
  expect(screen.getByText(/Не тот стек/, { selector: "span" })).toBeInTheDocument();
  expect(screen.getByText(/Отклонён · не тот стек/)).toBeInTheDocument();
});

const candOffer = (id: string, status: string, extra: Record<string, unknown> = {}) => ({
  id, status, created_at: "2026-10-02T10:00:00Z", expires_at: "2026-10-16T10:00:00Z",
  vacancy: { id: "v1", title: "Backend (Python)", role: "backend", grade_min: "middle", grade_max: "middle_plus", formats: ["remote"], employment_type: "full" },
  salary_from: 200000, salary_to: 250000, below_candidate_min: false, match_snapshot: null, decline: null,
  company: { id: "c1", name: "Северный код", responsibility_score: 4.6, verified: true }, ...extra,
});

function stubCandidate(list: unknown[]) {
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/me")) return res(200, { id: "u2", email: "c@b.ru", role: "candidate", consents: ["pd_processing"] });
    if (url.endsWith("/candidates/me/offers")) return res(200, list);
    if (/\/offers\/o\d\/(messages|events)/.test(url)) return res(200, []);
    const m = /\/offers\/(o\d)$/.exec(url);
    if (m && init?.method !== "POST") return res(200, list.find((o) => (o as { id: string }).id === m[1]));
    if (/\/offers\/o\d\/decline$/.test(url)) {
      calls.push({ url, headers: new Headers(init?.headers), body: JSON.parse(String(init?.body)) });
      return res(200, candOffer("o1", "declined"));
    }
    return base(url, init);
  });
}

test("M2: приглашение без вакансии показывается по названию, плашка «ниже ожиданий», сводка прошлых", async () => {
  stubCandidate([
    candOffer("o1", "sent", { below_candidate_min: true }),
    candOffer("o2", "sent", { vacancy: null, title: "Рекрутинг ML-команды", initiator: "employer" }),
    candOffer("o3", "declined"),
    candOffer("o4", "expired"),
  ]);
  mount("/me/offers");
  expect(await screen.findByText("Рекрутинг ML-команды")).toBeInTheDocument();
  expect(screen.getByText("Приглашение без вакансии")).toBeInTheDocument();
  expect(screen.getByText("Ниже ваших ожиданий")).toBeInTheDocument();
  expect(screen.getByText("2 новых")).toBeInTheDocument();
  expect(screen.getByText(/принято 0 · отклонено 1 · истёк 1/)).toBeInTheDocument();
});

test("M2: отказ одним тапом по причине в нижнем листе", async () => {
  stubCandidate([candOffer("o1", "sent")]);
  mount("/me/offers/o1");
  fireEvent.click(await screen.findByRole("button", { name: "Не подходит" }));
  fireEvent.click(await screen.findByRole("button", { name: /Не тот стек/ }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body).toEqual({ reason: "wrong_stack", comment: null });
});

test("M2: детали приглашения без вакансии открываются", async () => {
  stubCandidate([candOffer("o2", "accepted", { vacancy: null, title: "Рекрутинг ML-команды", description: "Нужен тимлид" })]);
  mount("/me/offers/o2");
  expect(await screen.findByRole("heading", { name: "Приглашение принят" })).toBeInTheDocument();
  expect(screen.getByText("Нужен тимлид")).toBeInTheDocument();
  expect(screen.getByText(/Рекрутинг ML-команды/)).toBeInTheDocument();
});

test("E32-7: кандидат отзывает доступ к контактам через подтверждение", async () => {
  stubCandidate([candOffer("o2", "accepted")]);
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (/\/offers\/o2\/contacts\/revoke$/.test(url)) {
      calls.push({ url, headers: new Headers(init?.headers), body: null });
      return res(200, candOffer("o2", "accepted", { contacts_revoked_at: "2026-10-05T10:00:00Z" }));
    }
    return base(url, init);
  });
  mount("/me/offers/o2");
  fireEvent.click(await screen.findByRole("button", { name: "Отозвать доступ к контактам" }));
  fireEvent.click(await screen.findByRole("button", { name: "Отозвать" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].url).toMatch(/\/offers\/o2\/contacts\/revoke$/);
});

test("E32-7: после отзыва кнопки нет, показана пометка; чат на месте", async () => {
  stubCandidate([candOffer("o2", "accepted", { contacts_revoked_at: "2026-10-05T10:00:00Z" })]);
  mount("/me/offers/o2");
  expect(await screen.findByText(/Вы отозвали доступ к контактам/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Отозвать доступ к контактам" })).toBeNull();
  expect(screen.getByRole("region", { name: "Переписка" })).toBeInTheDocument();
});
