import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

interface Call {
  url: string;
  method: string;
  body: unknown;
}

const calls: Call[] = [];
let consentsGranted = false;
let loggedIn = false;

const consentList = () =>
  ["pd_processing", "fsp_data", "code_analysis", "telegram_notifications", "public_profile"].map((type) => ({
    type,
    required: type === "pd_processing",
    granted: type === "pd_processing" && consentsGranted,
    version: null,
    current_version: "2025-09-01",
    granted_at: null,
  }));

function respond(status: number, body?: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), { status });
}

function installFetch(opts: { loginStatus?: number; loginCode?: string; magicStatus?: number; meFailsOnce?: boolean } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ url, method, body });
      if (url.endsWith("/auth/refresh")) return respond(401);
      if (url.endsWith("/auth/login")) {
        if (opts.loginStatus && opts.loginStatus !== 200) return respond(opts.loginStatus, { code: opts.loginCode });
        loggedIn = true;
        return respond(200, { access_token: "t", user: { id: "u1", email: "a@b.ru", role: "candidate" } });
      }
      if (url.endsWith("/auth/register")) {
        if (opts.loginStatus === 409) return respond(409, { code: "email_taken" });
        loggedIn = true;
        return respond(201, { access_token: "t", user: { id: "u1", email: body.email, role: body.role } });
      }
      if (url.endsWith("/auth/magic")) {
        if (opts.magicStatus && opts.magicStatus !== 200) return respond(opts.magicStatus, { code: "invalid_magic_token" });
        loggedIn = true;
        return respond(200, { access_token: "t", user: { id: "u1", email: null, role: "candidate" } });
      }
      if (url.endsWith("/me/consents") && method === "PUT") {
        consentsGranted = body.consents.some((c: { type: string; granted: boolean }) => c.type === "pd_processing" && c.granted);
        return respond(200, consentList());
      }
      if (url.endsWith("/me/consents")) return respond(200, consentList());
      if (url.endsWith("/me")) {
        if (opts.meFailsOnce && loggedIn) {
          opts.meFailsOnce = false;
          return respond(401);
        }
        return loggedIn
          ? respond(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: consentsGranted ? ["pd_processing"] : [] })
          : respond(401);
      }
      return respond(404);
    }),
  );
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

class FakeES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  calls.length = 0;
  consentsGranted = false;
  loggedIn = false;
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("вход без согласия ведёт на экран согласий, после согласия — в кабинет", async () => {
  installFetch();
  mount("/login");
  fireEvent.change(await screen.findByLabelText("Почта"), { target: { value: "a@b.ru" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "secret-pass" } });
  fireEvent.click(screen.getByRole("button", { name: "Войти" }));

  expect(await screen.findByRole("heading", { name: "Согласия" })).toBeInTheDocument();
  const submit = await screen.findByRole("button", { name: "Продолжить" });
  expect(submit).toBeDisabled();
  // только обязательные: необязательные — в настройках, выключены
  expect(screen.getAllByRole("checkbox")).toHaveLength(1);
  expect(screen.queryByTestId("consents-item-fsp_data")).toBeNull();

  fireEvent.click(screen.getByRole("checkbox", { name: /Обработка персональных данных/ }));
  expect(submit).toBeEnabled();
  fireEvent.click(submit);

  expect(await screen.findByRole("heading", { name: "Главная" })).toBeInTheDocument();
  const put = calls.find((c) => c.method === "PUT");
  expect(put?.body).toEqual({ consents: [{ type: "pd_processing", granted: true, version: "2025-09-01" }] });
});

test("неверный пароль показывает ошибку и остаётся на форме", async () => {
  installFetch({ loginStatus: 401, loginCode: "invalid_credentials" });
  mount("/login");
  fireEvent.change(await screen.findByLabelText("Почта"), { target: { value: "a@b.ru" } });
  fireEvent.change(screen.getByLabelText("Пароль"), { target: { value: "bad" } });
  fireEvent.click(screen.getByRole("button", { name: "Войти" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Неверная почта или пароль");
  expect(screen.getByRole("button", { name: "Войти" })).toBeEnabled();
});

test("регистрация отправляет выбранную роль, занятая почта — понятная ошибка", async () => {
  installFetch();
  mount("/register");
  fireEvent.click(await screen.findByLabelText(/Я ищу людей/));
  fireEvent.change(screen.getByLabelText("Почта"), { target: { value: "hr@company.ru" } });
  fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "long-enough-pass" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /обработку персональных данных/ }));
  fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/auth/register"))?.body).toEqual({
    email: "hr@company.ru",
    password: "long-enough-pass",
    role: "employer",
  }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/me/consents") && c.method === "PUT")).toBe(true));
  expect(screen.queryByRole("heading", { name: "Согласия" })).toBeNull();
});

test("новый кандидат: согласие в форме регистрации → сразу шаг 1 потока до теста", async () => {
  installFetch();
  mount("/register");
  fireEvent.change(await screen.findByLabelText("Почта"), { target: { value: "new@b.ru" } });
  fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "long-enough-pass" } });
  fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  // без обязательного согласия аккаунт не создаётся
  expect(await screen.findByTestId("auth-need-consent")).toBeInTheDocument();
  expect(calls.some((c) => c.url.endsWith("/auth/register"))).toBe(false);
  fireEvent.click(screen.getByRole("checkbox", { name: /обработку персональных данных/ }));
  fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  expect(await screen.findByRole("heading", { name: "Направление и навыки" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Согласия" })).toBeNull();
  // выдано только обязательное согласие, необязательные остаются выключенными
  const put = calls.find((c) => c.url.endsWith("/me/consents") && c.method === "PUT")!;
  expect(put.body).toEqual({ consents: [{ type: "pd_processing", granted: true }] });
});

test("регистрация: email_taken", async () => {
  installFetch({ loginStatus: 409 });
  mount("/register");
  fireEvent.change(await screen.findByLabelText("Почта"), { target: { value: "a@b.ru" } });
  fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "long-enough-pass" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /обработку персональных данных/ }));
  fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("уже зарегистрирована");
});

test("magic-ссылка: токен отправляется один раз и ведёт на redirect", async () => {
  installFetch();
  consentsGranted = true;
  mount("/auth/magic?token=abc&redirect=/me/offers");
  expect(await screen.findByRole("heading", { name: "Приглашения" })).toBeInTheDocument();
  const magic = calls.filter((c) => c.url.endsWith("/auth/magic"));
  expect(magic).toHaveLength(1);
  expect(magic[0].body).toEqual({ token: "abc" });
});

test("magic-ссылка: чужой redirect игнорируется", async () => {
  installFetch();
  consentsGranted = true;
  mount("/auth/magic?token=abc&redirect=//evil.example");
  expect(await screen.findByRole("heading", { name: "Главная" })).toBeInTheDocument();
});

test("magic-ссылка: недействительный токен", async () => {
  installFetch({ magicStatus: 401 });
  mount("/auth/magic?token=old");
  expect(await screen.findByRole("alert")).toHaveTextContent("недействительна");
});

test("аноним на /consents уходит на вход", async () => {
  installFetch();
  mount("/consents");
  expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
});

test("регистрация: сбой чтения профиля после неё не даёт «Неверная почта или пароль»", async () => {
  installFetch({ meFailsOnce: true });
  mount("/register");
  fireEvent.change(await screen.findByLabelText("Почта"), { target: { value: "new@b.ru" } });
  fireEvent.change(screen.getByLabelText(/Пароль/), { target: { value: "long-enough-pass" } });
  fireEvent.click(screen.getByRole("checkbox", { name: /обработку персональных данных/ }));
  fireEvent.click(screen.getByRole("button", { name: "Создать аккаунт" }));
  expect(await screen.findByRole("heading", { name: "Направление и навыки" })).toBeInTheDocument();
  expect(screen.queryByText("Неверная почта или пароль")).toBeNull();
});
