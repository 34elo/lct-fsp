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

test("тексты ошибок оффера по code", () => {
  expect(offerErrorText(new ApiError(429, "offer_limit_exceeded", {}))).toMatch(/Лимит офферов/);
  expect(offerErrorText(new ApiError(409, "offer_exists", {}))).toMatch(/уже отправлен/);
  expect(offerErrorText(new ApiError(422, "salary_range_required", {}))).toMatch(/вилку/);
  expect(offerErrorText(new ApiError(429, undefined, {}))).toMatch(/Слишком много/);
});

test("форма оффера: подсказка p_accept и предупреждения, ключ идемпотентности, текст ошибки 429", async () => {
  mount("/employer/offers/new?candidate=p1&vacancy=v1");
  expect(await screen.findByText(/Вероятность принятия: низкая/)).toBeInTheDocument();
  expect(screen.getByText(/ниже ожиданий кандидата/i)).toBeInTheDocument();
  expect(screen.getByText(/Слишком широкая вилка/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Отправить оффер" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/Лимит офферов на сутки/);
  expect(calls[0].headers.get("Idempotency-Key")).toMatch(/.{8,}/);
  expect(calls[0].body).toMatchObject({ vacancy_id: "v1", candidate_pseudo_id: "p1", salary_from: 200000, salary_to: 280000 });
});

test("пустая вилка не отправляется", async () => {
  mount("/employer/offers/new?candidate=p1&vacancy=v1");
  await screen.findByText(/Вероятность принятия/);
  const [from] = screen.getAllByRole("textbox", { name: /от/ });
  fireEvent.change(from, { target: { value: "" } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить оффер" }));
  await waitFor(() => expect(screen.getAllByText(/Укажите обе границы вилки/).length).toBeGreaterThan(0));
  expect(calls).toHaveLength(0);
});
