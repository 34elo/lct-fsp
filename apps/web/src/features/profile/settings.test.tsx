import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const json = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const profile = {
  pseudonym: "Backend #4821",
  profile_version: 3,
  search_status: "active",
  preferences: { work_format: [], relocation: false },
  visibility: { full_name: false, companies: true, fsp: true, region: true, education: false, repos: false, public_profile: false, teams: true },
  grade: { breakdown: [] },
  skills: [],
  team_signals: [],
};
const consent = (type: string, required: boolean, granted: boolean) => ({ type, required, granted, version: "v1", current_version: "v1", granted_at: null });
const consents = (pd = true) => [
  consent("pd_processing", true, pd),
  consent("profile_publication", false, true),
  consent("telegram_notifications", false, false),
];

class FakeES {
  addEventListener() {}
  close() {}
}

function install(opts: { pd?: boolean; consentsStatus?: number; telegramLinked?: boolean } = {}) {
  const visibility: unknown[] = [];
  const puts: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "t" });
      if (url.endsWith("/me")) return json(200, { id: "u1", email: "a@b.ru", role: "candidate", email_verified: true, consents: ["pd_processing"], telegram_linked: opts.telegramLinked ?? false });
      if (url.endsWith("/candidates/me/visibility") && init?.method === "PATCH") {
        visibility.push(JSON.parse(String(init.body)));
        return json(200, profile);
      }
      if (url.endsWith("/candidates/me/profile")) return json(200, profile);
      if (url.endsWith("/me/consents") && init?.method === "PUT") {
        puts.push(JSON.parse(String(init.body)));
        return json(200, consents(opts.pd));
      }
      if (url.endsWith("/me/consents")) return opts.consentsStatus ? json(opts.consentsStatus, { code: "unavailable" }) : json(200, consents(opts.pd));
      if (url.endsWith("/me/telegram/link")) return json(200, { deep_link: "https://t.me/bot?start=link_x" });
      return json(404);
    }),
  );
  return { visibility, puts };
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/me/settings"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("приватность: умолчания и переключатель сразу уходит в PATCH visibility", async () => {
  const { visibility } = install();
  mount();
  expect(await screen.findByTestId("privacy-full_name")).not.toBeChecked();
  expect(screen.getByTestId("privacy-companies")).toBeChecked();
  expect(screen.getByTestId("privacy-fsp")).toBeChecked();
  expect(screen.getByTestId("privacy-region")).toBeChecked();
  fireEvent.click(screen.getByTestId("privacy-full_name"));
  await waitFor(() => expect(visibility).toContainEqual({ full_name: true }));
  fireEvent.click(screen.getByTestId("privacy-region"));
  await waitFor(() => expect(visibility).toContainEqual({ region: false }));
});

test("согласия: обязательное не отзывается, необязательное уходит в PUT с версией", async () => {
  const { puts } = install();
  mount();
  expect(await screen.findByTestId("settings-consent-pd_processing")).toBeDisabled();
  expect(screen.getByTestId("settings-consent-pd_processing")).toBeChecked();
  fireEvent.click(screen.getByTestId("settings-consent-profile_publication"));
  await waitFor(() => expect(puts).toContainEqual({ consents: [{ type: "profile_publication", granted: false, version: "v1" }] }));
  fireEvent.click(screen.getByTestId("settings-consent-telegram_notifications"));
  await waitFor(() => expect(puts).toContainEqual({ consents: [{ type: "telegram_notifications", granted: true, version: "v1" }] }));
});

test("уведомления: Telegram привязан — статус, не привязан — кнопка", async () => {
  install({ telegramLinked: true });
  mount();
  expect(await screen.findByTestId("settings-telegram-linked")).toHaveTextContent("привязан");
  expect(screen.queryByTestId("settings-telegram-link")).toBeNull();
});

test("уведомления: без привязки есть кнопка", async () => {
  install();
  mount();
  expect(await screen.findByTestId("settings-telegram-link")).toBeInTheDocument();
});

test("пустое состояние: нет согласия на ПДн — одна кнопка «Дать согласие»", async () => {
  install({ pd: false });
  mount();
  expect(await screen.findByText("Согласия не даны — профиль скрыт от компаний")).toBeInTheDocument();
  expect(screen.getByTestId("settings-empty-action")).toHaveAttribute("href", "/consents");
  expect(screen.queryByTestId("privacy-settings")).toBeNull();
});

test("ошибка: «Не загрузилось» с кодом и повтором", async () => {
  install({ consentsStatus: 503 });
  mount();
  const box = await screen.findByTestId("settings-error-state");
  expect(box).toHaveTextContent("Не загрузилось");
  expect(box).toHaveTextContent("ошибка 503");
});

test("меню аватара кандидата ведёт в «Настройки»", async () => {
  install();
  render(
    <MemoryRouter initialEntries={["/me/stats"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  const btn = await screen.findByRole("button", { name: /Меню аккаунта/ });
  fireEvent.pointerDown(btn, { button: 0, ctrlKey: false });
  fireEvent.keyDown(btn, { key: "Enter" });
  fireEvent.click(await screen.findByRole("menuitem", { name: "Настройки" }));
  expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
});

test("оформление: две темы, выбор сохраняется", async () => {
  install();
  mount();
  fireEvent.click(await screen.findByTestId("settings-theme-dark"));
  expect(screen.getByTestId("settings-theme-dark")).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByTestId("settings-theme-light")).toHaveAttribute("aria-pressed", "false");
  expect(localStorage.getItem("fsp-theme")).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  fireEvent.click(screen.getByTestId("settings-theme-light"));
  expect(document.documentElement.classList.contains("dark")).toBe(false);
});
