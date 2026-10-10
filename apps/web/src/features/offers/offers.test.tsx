import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  return render(
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

test("E38-13: воронка, таблица предложений, последняя переписка и отклики", async () => {
  const list = [
    mkOffer("1", "interest", { interest_at: "2026-10-02T10:00:00Z" }),
    mkOffer("2", "interest_opened", { interest_at: "2026-10-02T10:00:00Z", interest_opened_at: "2026-10-03T10:00:00Z" }),
    mkOffer("3", "sent"),
    mkOffer("4", "accepted", { invited_at: "2026-10-03T10:00:00Z", contacts: { name: "Иван" } }),
    mkOffer("5", "sent", { initiator: "candidate" }),
  ];
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/offers") && init?.method !== "POST") return res(200, list);
    return base(url, init);
  });
  mount("/employer/offers");
  const rows = await screen.findAllByTestId("offer-row");
  expect(rows).toHaveLength(4);
  expect(within(screen.getByRole("region", { name: "Воронка" })).getByText("интерес").previousElementSibling).toHaveTextContent("2");
  expect(screen.getByRole("heading", { name: "Предложения" })).toBeInTheDocument();
  expect(await screen.findByText("Контакты открыты")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть" })).toHaveAttribute("href", "/employer/offers/4");
  const resp = screen.getByRole("region", { name: "Отклики на вакансии" });
  expect(within(resp).getByText("Backend #5")).toBeInTheDocument();
  expect(within(resp).getByRole("link", { name: "Все отклики" })).toHaveAttribute("href", "/employer/offers?show=responses");
});

test("E38-13: пустой список и ошибка загрузки", async () => {
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => (url.endsWith("/offers") && init?.method !== "POST" ? res(200, []) : base(url, init)));
  const first = mount("/employer/offers");
  expect(await screen.findByText("Приглашений пока нет")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Перейти к подбору" })).toHaveAttribute("href", "/employer");
  first.unmount();
  f.mockImplementation(async (url: string, init?: RequestInit) => (url.endsWith("/offers") && init?.method !== "POST" ? res(503, { type: "x", title: "x", status: 503, code: "down" }) : base(url, init)));
  mount("/employer/offers");
  expect(await screen.findByText("ошибка 503", {}, { timeout: 6000 })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
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
  expect(screen.getByText("Ниже ваших ожиданий")).toBeInTheDocument();
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

test("E32-7: после отзыва кнопки нет, показана пометка; чата нет (E39-26)", async () => {
  stubCandidate([candOffer("o2", "accepted", { contacts_revoked_at: "2026-10-05T10:00:00Z" })]);
  mount("/me/offers/o2");
  expect(await screen.findByText(/Вы отозвали доступ к контактам/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Отозвать доступ к контактам" })).toBeNull();
  expect(screen.queryByTestId("offer-reply")).toBeNull();
  expect(screen.queryByRole("region", { name: "Переписка" })).toBeNull();
});

test("E38-14: список приглашений — карточки v2, «Принять» из списка, прошлые со статусом, отклики не показываются", async () => {
  stubCandidate([
    candOffer("o1", "sent", { why_you: { factors: [{ code: "skills", text: "Python подтверждён тестом", weight: 1 }], unconfirmed: [] } }),
    candOffer("o2", "expired"),
    candOffer("o3", "sent", { initiator: "candidate", vacancy: { ...candOffer("x", "sent").vacancy, title: "Свой отклик" } }),
  ]);
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (/\/offers\/o1\/accept$/.test(url)) {
      calls.push({ url, headers: new Headers(init?.headers), body: null });
      return res(200, candOffer("o1", "accepted"));
    }
    return base(url, init);
  });
  mount("/me/offers");
  expect(await screen.findByText("Python подтверждён тестом")).toBeInTheDocument();
  expect(screen.getAllByText("200–250 тыс. ₽")).toHaveLength(2);
  expect(screen.queryByText("Свой отклик")).toBeNull();
  expect(screen.getByText("Истёк")).toBeInTheDocument();
  expect(screen.getAllByRole("link", { name: "Подробнее" })[0]).toHaveAttribute("href", "/me/offers/o1");
  fireEvent.click(screen.getByRole("button", { name: /^Принять/ }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].url).toMatch(/\/offers\/o1\/accept$/);
});

test("E38-14: «Отклонить» в списке — причина одним тапом", async () => {
  stubCandidate([candOffer("o1", "sent")]);
  mount("/me/offers");
  fireEvent.click(await screen.findByRole("button", { name: "Отклонить" }));
  fireEvent.click(await screen.findByRole("button", { name: /Мало денег/ }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body).toEqual({ reason: "low_salary", comment: null });
});

test("E38-14: пустой список и ошибка загрузки приглашений", async () => {
  stubCandidate([]);
  const first = mount("/me/offers");
  expect(await screen.findByText("Пока никто не пригласил")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Смотреть вакансии" })).toHaveAttribute("href", "/jobs");
  first.unmount();
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => (url.endsWith("/candidates/me/offers") ? res(503, { type: "x", title: "x", status: 503, code: "down" }) : base(url, init)));
  mount("/me/offers");
  expect(await screen.findByText("ошибка 503", {}, { timeout: 6000 })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
});

test("E39-24: приглашение подписано HR (имя, должность, аватар), «О компании» в Markdown", async () => {
  stubCandidate([
    candOffer("o1", "sent", {
      initiator: "employer",
      sender: { full_name: "Мария Рекрутова", position: "HR-партнёр", avatar_url: "/users/u9/avatar?v=abc" },
      company: { id: "c1", name: "Северный код", responsibility_score: 4.6, verified: true, description: "Делаем **платформы**" },
    }),
  ]);
  mount("/me/offers/o1");
  const sender = await screen.findByTestId("offer-sender");
  expect(within(sender).getByText("Мария Рекрутова")).toBeInTheDocument();
  expect(within(sender).getByText("HR-партнёр · Северный код")).toBeInTheDocument();
  expect(sender.querySelector("img")?.getAttribute("src") ?? "").toMatch(/\/users\/u9\/avatar\?v=abc$/);
  const about = screen.getByTestId("offer-company-about");
  expect(within(about).getByText("платформы").tagName).toBe("STRONG");
});

test("E39-24: без подписи блока отправителя нет", async () => {
  stubCandidate([candOffer("o1", "sent", { initiator: "employer", sender: null })]);
  mount("/me/offers/o1");
  expect(await screen.findByText("Северный код", { exact: false })).toBeInTheDocument();
  expect(screen.queryByTestId("offer-sender")).toBeNull();
});

test("E41-4: «Принять» уходит без текста; поля ответа и кнопок переписки нет", async () => {
  stubCandidate([candOffer("o1", "sent", { message: "Рады пригласить", task: { title: "Мини-кейс", minutes: 15, deadline_at: "2026-10-12T10:00:00Z" } })]);
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (/\/offers\/o1\/accept$/.test(url)) {
      calls.push({ url, headers: new Headers(init?.headers), body: init?.body ? JSON.parse(String(init.body)) : null });
      return res(200, candOffer("o1", "accepted"));
    }
    return base(url, init);
  });
  mount("/me/offers/o1");
  expect(await screen.findByTestId("offer-message")).toHaveTextContent("Рады пригласить");
  expect(screen.getByTestId("offer-task")).toHaveTextContent("Мини-кейс");
  expect(screen.queryByRole("button", { name: "Задать вопрос" })).toBeNull();
  expect(screen.queryByRole("textbox")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Принять" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0].body).toBeNull();
});

test("E39-26: после принятия кандидат видит контакты компании и кнопку «Написать в Telegram»", async () => {
  stubCandidate([candOffer("o1", "accepted", { company_contacts: { name: "Северный код", email: "hr@north.example", phone: "+7 900 000-00-00", telegram: "@north_hr" } })]);
  mount("/me/offers/o1");
  const box = await screen.findByTestId("company-contacts");
  expect(within(box).getByText("hr@north.example")).toBeInTheDocument();
  expect(within(box).getByText("+7 900 000-00-00")).toBeInTheDocument();
  expect(within(box).getByRole("link", { name: "Написать в Telegram" })).toHaveAttribute("href", "https://t.me/north_hr");
});

test("E41-4: работодатель видит контакты кандидата после принятия, ответа кандидата нет", async () => {
  const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
  const base = f.getMockImplementation()!;
  const offer = {
    id: "e1", status: "accepted", created_at: "2026-10-02T10:00:00Z", expires_at: "2026-10-16T10:00:00Z", vacancy: null, title: "Прямое",
    salary_from: 200000, salary_to: 250000, below_candidate_min: false, message: "Здравствуйте", candidate: card,
    contacts: { name: "Candidate #1", email: "c@x.ru", phone: "+7 911 111-11-11", telegram: "@cand_1" },
  };
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (/\/offers\/e1\/events$/.test(url)) return res(200, []);
    if (/\/offers\/e1$/.test(url)) return res(200, offer);
    return base(url, init);
  });
  mount("/employer/offers/e1");
  expect(await screen.findByTestId("offer-message")).toHaveTextContent("Здравствуйте");
  const box = screen.getByTestId("candidate-contacts");
  expect(within(box).getByText("c@x.ru")).toBeInTheDocument();
  expect(within(box).getByRole("link", { name: "Написать в Telegram" })).toHaveAttribute("href", "https://t.me/cand_1");
  expect(screen.queryByTestId("offer-reply")).toBeNull();
  expect(screen.queryByRole("region", { name: "Переписка" })).toBeNull();
});
