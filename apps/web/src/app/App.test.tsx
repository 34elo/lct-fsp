import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";
import { Providers, makeQueryClient } from "./Providers";
import { setAccessToken } from "@/shared/lib/token";

type Handler = (url: string, init?: RequestInit) => { status: number; body?: unknown };

function mockFetch(h: Handler) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const r = h(url, init);
      return new Response(r.body === undefined ? null : JSON.stringify(r.body), { status: r.status });
    }),
  );
}

class FakeES {
  static last: FakeES | null = null;
  constructor(public url: string) {
    FakeES.last = this;
  }
  addEventListener() {}
  close() {}
}

function mount(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

const asUser = (role: string) =>
  mockFetch((url) =>
    url.endsWith("/auth/refresh")
      ? { status: 200, body: { access_token: "t" } }
      : url.endsWith("/candidates/me/profile")
        ? { status: 404 }
        : { status: 200, body: { id: "u1", email: "a@b.ru", role, consents: ["pd_processing"] } },
  );

beforeEach(() => {
  setAccessToken(null);
  FakeES.last = null;
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("публичный лендинг доступен без входа", async () => {
  mockFetch(() => ({ status: 401 }));
  mount("/");
  expect(await screen.findByRole("heading", { level: 1, name: "Тест подтверждает грейд. Работодатель приходит с вилкой." })).toBeInTheDocument();
});

test("аноним на /me уходит на форму входа", async () => {
  mockFetch(() => ({ status: 401 }));
  mount("/me");
  expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
});

test("кандидат видит свой кабинет и открывает SSE", async () => {
  asUser("candidate");
  mount("/me");
  expect(await screen.findByRole("heading", { name: "Главная" })).toBeInTheDocument();
  await waitFor(() => expect(FakeES.last?.url).toContain("/events/stream?access_token=t"));
});

test("кандидат не попадает в раздел работодателя", async () => {
  asUser("candidate");
  mount("/employer/search");
  expect(await screen.findByRole("heading", { name: "Главная" })).toBeInTheDocument();
});

test("админ ФСП видит главную админки", async () => {
  asUser("fsp_admin");
  mount("/federation");
  expect(await screen.findByRole("heading", { name: "Главная" })).toBeInTheDocument();
});

test("неизвестный путь — 404", async () => {
  mockFetch(() => ({ status: 401 }));
  mount("/nope");
  expect(await screen.findByRole("heading", { name: "Страница не найдена" })).toBeInTheDocument();
});
