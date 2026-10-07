import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const vac = {
  id: "v1", company_id: "c1", title: "Backend (Python)", role: "backend", grade_min: "middle", grade_max: "middle_plus",
  formats: ["remote"], employment_type: "full", city: null, salary_from: 200000, salary_to: 250000, range_too_wide: false,
  description: null, status: "published", important_qualities: [], skills: [], version: 1,
  created_at: "2026-10-01T00:00:00Z", published_at: "2026-10-01T00:00:00Z",
};
const card = {
  pseudo_id: "p1", pseudonym: "Candidate #1", avatar_seed: "abc", primary_role: "backend", grade: "middle", grade_preliminary: false,
  primary_stack: ["python"], top_skills: [], fsp_highlights: [], salary_min: 230000, formats: ["remote"], city: null, relocation: false,
  search_status: "active", updated_at: "2026-10-02T00:00:00Z", skills: [], grade_info: { breakdown: [] }, experience: [], offers_from_you: [],
};
const posts: { headers: Headers; body: Record<string, unknown> }[] = [];

beforeEach(() => {
  posts.length = 0;
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
        return res(200, { candidate_min: 230000, below_candidate_min: false, category_median: 275000, p_accept: 0.7, acceptance_hint: "high", range_too_wide: false, message: "" });
      }
      if (url.endsWith("/offers") && init?.method === "POST") {
        posts.push({ headers: new Headers(init.headers), body: JSON.parse(String(init.body)) });
        return res(429, { code: "offer_limit_exceeded", status: 429 });
      }
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

async function openDialog() {
  render(
    <MemoryRouter initialEntries={["/employer/candidates/p1?vacancy=v1"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Отправить приглашение" }));
  return await screen.findByRole("dialog");
}
const sendBtn = () => screen.getAllByRole("button", { name: "Отправить приглашение" }).at(-1) as HTMLButtonElement;

test("модалка: вилка вакансии, медиана и AcceptanceMeter из API, ключ идемпотентности", async () => {
  await openDialog();
  expect(await screen.findByLabelText(/Вероятность принятия: высокая/)).toBeInTheDocument();
  expect(screen.getByText(/Медиана категории/)).toBeInTheDocument();
  expect(screen.getByText(/не ниже ожиданий кандидата/)).toBeInTheDocument();
  fireEvent.click(sendBtn());
  expect(await screen.findByText(/Лимит приглашений на сутки/)).toBeInTheDocument();
  expect(posts[0].headers.get("Idempotency-Key")).toMatch(/.{8,}/);
  expect(posts[0].body).toMatchObject({ vacancy_id: "v1", candidate_pseudo_id: "p1", salary_from: 200000, salary_to: 250000 });
});

test("«Отправить» заблокирована без вилки и при «до < от», широкая вилка предупреждает", async () => {
  await openDialog();
  await screen.findByLabelText(/Вероятность принятия/);
  const [from, to] = screen.getAllByRole("textbox").filter((e) => e.getAttribute("inputmode") === "numeric");
  fireEvent.change(to, { target: { value: "150000" } });
  expect(sendBtn()).toBeDisabled();
  fireEvent.change(to, { target: { value: "" } });
  expect(sendBtn()).toBeDisabled();
  fireEvent.change(to, { target: { value: "400000" } });
  expect(sendBtn()).toBeEnabled();
  expect(screen.getByText(/Слишком широкая вилка/)).toBeInTheDocument();
  fireEvent.change(from, { target: { value: "" } });
  expect(sendBtn()).toBeDisabled();
  expect(posts).toHaveLength(0);
});

test("без вакансии название обязательно, уходит vacancy_id=null и title", async () => {
  await openDialog();
  await screen.findByLabelText(/Вероятность принятия/);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "" } });
  const [from, to] = screen.getAllByRole("textbox").filter((e) => e.getAttribute("inputmode") === "numeric");
  fireEvent.change(from, { target: { value: "200000" } });
  fireEvent.change(to, { target: { value: "240000" } });
  expect(sendBtn()).toBeDisabled();
  fireEvent.change(screen.getByLabelText(/Название приглашения/), { target: { value: "Бэкенд" } });
  expect(sendBtn()).toBeEnabled();
  fireEvent.change(screen.getByLabelText(/О чём приглашение/), { target: { value: "Команда платформы" } });
  fireEvent.change(screen.getByLabelText(/Как связаться/), { target: { value: "telegram" } });
  fireEvent.click(sendBtn());
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0].body).toMatchObject({ vacancy_id: null, title: "Бэкенд", description: "Команда платформы", contact_method: "telegram", salary_from: 200000, salary_to: 240000 });
});
