import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const posts: { url: string; body: unknown }[] = [];

beforeEach(() => {
  posts.length = 0;
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || (url.endsWith("/me") && !url.includes("/companies"))) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      if (url.includes("/companies/me")) return res(200, { id: "c1", name: "Acme", inn: null, site: null, description: null, logo_key: null, status: "pending", responsibility_score: null, created_at: "2026-10-01T00:00:00Z", my_role: "admin" });
      if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "python", name: "Python", kind: "hard" }] });
      if (url.includes("/vacancies") && init?.method === "POST") {
        posts.push({ url, body: JSON.parse(String(init.body)) });
        return res(201, { id: "v9" });
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

test("редактор: широкая вилка предупреждает, пустая вилка не уходит, навык и качество попадают в тело", async () => {
  mount("/employer/vacancies/new");
  fireEvent.change(await screen.findByLabelText("Название вакансии"), { target: { value: "Backend" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить черновик" }));
  expect(await screen.findByText("Вилка обязательна: укажите обе границы.")).toBeInTheDocument();
  expect(posts).toHaveLength(0);

  fireEvent.change(screen.getByLabelText("от"), { target: { value: "100000" } });
  fireEvent.change(screen.getByLabelText("до"), { target: { value: "200000" } });
  expect(screen.getByText(/Слишком широкая вилка/)).toBeInTheDocument();

  fireEvent.change(screen.getByLabelText("Добавить навык"), { target: { value: "pyth" } });
  fireEvent.click(await screen.findByRole("button", { name: "Python в обязательные" }));
  fireEvent.click(screen.getByRole("radio", { name: "4 — эксперт" }));
  fireEvent.click(screen.getByRole("checkbox", { name: /Лидерство/ }));
  expect(await screen.findByText(/Компания ещё не проверена/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Сохранить черновик" }));
  await vi.waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0]!.body).toMatchObject({
    title: "Backend", salary_from: 100000, salary_to: 200000, important_qualities: ["leadership"],
    skills: [{ slug: "python", required: true, min_level: 4 }],
  });
});
