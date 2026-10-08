import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { applyErrorText, isUnverified } from "./text";
import { ApiError } from "@/api/mutator";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const vac = {
  id: "v1", title: "Python-разработчик (API)", role: "backend", grade_min: "middle", grade_max: "middle", formats: ["remote"],
  employment_type: "full", city: null, salary_from: 190000, salary_to: 230000, description: "Делаем API", published_at: "2026-10-01T00:00:00Z",
  skills: [{ slug: "python", required: true, min_level: 2, weight: 1 }], company: { id: "c1", name: "Север-Софт", verified: true, responsibility_score: 4 },
};
let role: string | null = null;
let applyResp: Response | null = null;
const applied: unknown[] = [];
const requested: string[] = [];

beforeEach(() => {
  setAccessToken(null);
  applied.length = 0;
  requested.length = 0;
  applyResp = null;
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return role ? res(200, { access_token: "t" }) : res(401);
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role, consents: ["pd_processing"] });
      if (url.includes("/vacancies/public/v1")) return res(200, vac);
      if (url.includes("/vacancies/public/")) return res(404, { code: "vacancy_not_found", status: 404 });
      if (url.includes("/vacancies/public")) {
        requested.push(url);
        return res(200, [vac]);
      }
      if (url.includes("/vacancies/v1/apply")) {
        applied.push(JSON.parse(String(init?.body)));
        return applyResp ?? res(201, { id: "o1" });
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

test("тексты ошибок отклика по code", () => {
  expect(applyErrorText(new ApiError(409, "already_applied", {}))).toMatch(/уже откликались/);
  expect(applyErrorText(new ApiError(429, "application_limit_exceeded", {}))).toMatch(/Лимит/);
  expect(isUnverified(new ApiError(403, "email_not_verified", {}))).toBe(true);
  expect(isUnverified(new ApiError(403, "other", {}))).toBe(false);
});

test("/jobs: публичный список без входа показывает вилку и ссылку на вакансию", async () => {
  mount("/jobs");
  expect(await screen.findByText("Python-разработчик (API)")).toBeInTheDocument();
  expect(screen.getByText(/190/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Подробнее" })).toHaveAttribute("href", "/jobs/v1");
});

test("/jobs/:id без входа: кнопка «Войти и откликнуться»", async () => {
  mount("/jobs/v1");
  expect(await screen.findByRole("link", { name: "Войти и откликнуться" })).toHaveAttribute("href", "/login");
});

test("кандидат откликается с сообщением; успех показывает статус", async () => {
  role = "candidate";
  mount("/jobs/v1");
  fireEvent.change(await screen.findByLabelText(/Сообщение компании/), { target: { value: "Привет" } });
  fireEvent.click(screen.getByRole("button", { name: "Откликнуться" }));
  expect(await screen.findByText("Отклик отправлен")).toBeInTheDocument();
  expect(applied).toEqual([{ message: "Привет" }]);
});

test("email не подтверждён: предупреждение и неактивная кнопка", async () => {
  role = "candidate";
  applyResp = res(403, { code: "email_not_verified", status: 403 });
  mount("/jobs/v1");
  fireEvent.click(await screen.findByRole("button", { name: "Откликнуться" }));
  expect(await screen.findByText("Email не подтверждён")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Откликнуться" })).toBeDisabled());
});

test("повторный отклик: понятная ошибка 409", async () => {
  role = "candidate";
  applyResp = res(409, { code: "already_applied", status: 409 });
  mount("/jobs/v1");
  fireEvent.click(await screen.findByRole("button", { name: "Откликнуться" }));
  expect(await screen.findByText(/уже откликались/)).toBeInTheDocument();
});

test("работодатель не видит формы отклика", async () => {
  role = "employer";
  mount("/jobs/v1");
  expect(await screen.findByText(/только кандидаты/)).toBeInTheDocument();
});

test("/jobs: фильтры читаются из URL и уходят в запрос", async () => {
  mount("/jobs?role=backend&grade=middle&format=remote&smin=150000&skills=python");
  expect(await screen.findByText("Python-разработчик (API)")).toBeInTheDocument();
  const u = new URL(requested[0], "http://x");
  expect(u.searchParams.get("role")).toBe("backend");
  expect(u.searchParams.get("grade")).toBe("middle");
  expect(u.searchParams.get("format")).toBe("remote");
  expect(u.searchParams.get("salary_min")).toBe("150000");
  expect(u.searchParams.getAll("skills")).toEqual(["python"]);
});

test("карточка: «Назад к списку» возвращает на список с теми же фильтрами", async () => {
  mount("/jobs?role=backend&grade=middle");
  fireEvent.click(await screen.findByRole("link", { name: "Подробнее" }));
  const back = await screen.findByRole("link", { name: /Назад к списку/ });
  expect(back).toHaveAttribute("href", "/jobs?role=backend&grade=middle");
});

test("карточка несуществующей вакансии: понятное сообщение", async () => {
  mount("/jobs/zzz");
  expect(await screen.findByText(/не найдена/)).toBeInTheDocument();
});
