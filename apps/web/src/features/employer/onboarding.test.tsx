import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const problem = (status: number, code: string) => res(status, { type: "x", title: "x", status, code });

const need = {
  id: "n1", text: "Backend на Python, Middle", filters: { roles: ["backend"] }, skills: {}, grades: ["middle"],
  shortlist: [], created_at: "2026-10-05T00:00:00Z",
  categories: [{ profession: "backend", title: "Backend", grade: "middle", affinity: 0.8, candidates: 0, median_salary: null, fsp_share: null }],
};

let company: { id: string; name: string; status: string; role: string } | null = null;
let calls: { method: string; url: string }[] = [];

beforeEach(() => {
  company = null;
  calls = [];
  localStorage.clear();
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"], company });
      calls.push({ method, url });
      // Как настоящий сервер: всё, что требует компанию, без неё отвечает 404.
      if (url.endsWith("/companies") && method === "POST") {
        company = { id: "co1", name: "Acme", status: "pending", role: "admin" };
        return res(201, { ...company, created_at: "2026-10-05T00:00:00Z" });
      }
      if (url.includes("/offers")) return res(200, []); // списки без компании пусты
      if (!company) return problem(404, "company_not_found");
      if (url.endsWith("/needs") && method === "POST") return res(201, need);
      if (url.includes("/needs/n1/categories")) return res(200, { need_id: "n1", shortlist: [], categories: need.categories });
      if (url.includes("/employer/activity")) return res(200, { items: [] });
      if (url.endsWith("/subscriptions")) return res(200, []);
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

const gated = (u: string) => /\/(employer\/activity|subscriptions|needs)(\?|\/|$)/.test(u);

test("новая компания: три шага онбординга без единого запроса, требующего компанию", async () => {
  mount("/employer");
  expect(await screen.findByTestId("employer-onboarding")).toBeInTheDocument();
  expect(screen.getByTestId("flow-step-1")).toHaveAttribute("aria-current", "step");

  // Шаг 1: название обязательно.
  fireEvent.click(screen.getByTestId("onboarding-company-submit"));
  expect(await screen.findByText(/Укажите название компании/)).toBeInTheDocument();
  fireEvent.change(screen.getByTestId("onboarding-company-name"), { target: { value: "Acme" } });
  fireEvent.click(screen.getByTestId("onboarding-company-submit"));

  // Шаг 2: первый запрос.
  const box = await screen.findByRole("textbox", { name: "Кого вы ищете" });
  expect(screen.getByTestId("flow-step-2")).toHaveAttribute("aria-current", "step");
  fireEvent.change(box, { target: { value: "Backend на Python, Middle" } });
  fireEvent.submit(box.closest("form")!);

  // Шаг 3: три карточки.
  const how = await screen.findByTestId("onboarding-how");
  expect(within(how).getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByTestId("onboarding-card-interest")).toHaveTextContent("вилк");
  fireEvent.click(screen.getByTestId("onboarding-done"));

  // Дальше — подбор по созданному запросу.
  // Условия запроса восстанавливаются в строке: профессия из текста — чипсом.
  expect(await screen.findByTestId("query-chip-profession")).toHaveTextContent("Backend");
  expect(screen.queryByTestId("employer-onboarding")).toBeNull();
  expect(JSON.parse(localStorage.getItem("fsp.employer.lastNeed") ?? "{}").company).toBe("co1");
  // До создания компании ни одного запроса, который дал бы 404.
  const before = calls.findIndex((c) => c.url.endsWith("/companies") && c.method === "POST");
  expect(calls.slice(0, before).filter((c) => gated(c.url))).toEqual([]);
});

test("пропустить: подбор показывает пустые состояния с действием и не ходит за данными компании", async () => {
  mount("/employer");
  fireEvent.click(await screen.findByTestId("onboarding-skip"));
  expect(await screen.findByText("Сначала расскажите о компании")).toBeInTheDocument();
  expect(within(screen.getByTestId("match-feed")).getByTestId("match-feed-empty")).toBeInTheDocument();
  expect(screen.queryByRole("textbox", { name: "Кого вы ищете" })).toBeNull();
  expect(calls.filter((c) => gated(c.url))).toEqual([]);

  // Повторно онбординг не навязывается, но запускается кнопкой.
  fireEvent.click(screen.getByTestId("match-setup"));
  expect(await screen.findByTestId("employer-onboarding")).toBeInTheDocument();
});

test("компания есть, активности нет: лента и подписки с действием", async () => {
  company = { id: "co1", name: "Acme", status: "pending", role: "admin" };
  mount("/employer?need=n1");
  const feed = await screen.findByTestId("match-feed");
  await waitFor(() => expect(within(feed).getByTestId("match-feed-empty")).toBeInTheDocument());
  expect(within(feed).getByRole("link", { name: "Подписаться на категорию" })).toHaveAttribute("href", "/employer/subscriptions");
  const subs = await screen.findByTestId("match-subscriptions-empty");
  expect(within(subs).getByRole("link", { name: "Подписаться на категорию" })).toBeInTheDocument();
  expect(screen.queryByTestId("employer-onboarding")).toBeNull();
});

test("крестик закрывает онбординг, и после перезагрузки он не появляется", async () => {
  mount("/employer");
  fireEvent.click(await screen.findByTestId("onboarding-close"));
  expect(await screen.findByText("Сначала расскажите о компании")).toBeInTheDocument();

  cleanup();
  mount("/employer");
  expect(await screen.findByText("Сначала расскажите о компании")).toBeInTheDocument();
  expect(screen.queryByTestId("employer-onboarding")).toBeNull();
});

test("«Больше не показывать» закрывает онбординг так же", async () => {
  mount("/employer");
  fireEvent.click(await screen.findByTestId("onboarding-dismiss"));
  expect(await screen.findByText("Сначала расскажите о компании")).toBeInTheDocument();
  expect(localStorage.getItem("fsp.employer.onboardingSkipped")).toBe("1");
});
