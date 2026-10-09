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

function install(opts: { pd?: boolean; consentsStatus?: number; telegramLinked?: boolean; role?: string; passwordStatus?: number; company?: boolean } = {}) {
  const visibility: unknown[] = [];
  const puts: unknown[] = [];
  const profilePatches: unknown[] = [];
  const passwords: unknown[] = [];
  const companyPatches: unknown[] = [];
  const staffPatches: unknown[] = [];
  const avatars: unknown[] = [];
  let staff = { full_name: "Анна", position: null as string | null, about: null as string | null, avatar_url: null as string | null };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "t" });
      if (url.endsWith("/me") && !url.endsWith("/companies/me")) return json(200, {
          id: "u1",
          email: "a@b.ru",
          role: opts.role ?? "candidate",
          email_verified: true,
          consents: ["pd_processing"],
          telegram_linked: opts.telegramLinked ?? false,
          company: opts.company ? { id: "c1", name: "Ромашка", status: "verified", role: "admin" } : null,
        });
      if (url.endsWith("/candidates/me/visibility") && init?.method === "PATCH") {
        visibility.push(JSON.parse(String(init.body)));
        return json(200, profile);
      }
      if (url.endsWith("/candidates/me/profile") && init?.method === "PATCH") {
        profilePatches.push(JSON.parse(String(init.body)));
        return json(200, profile);
      }
      if (url.endsWith("/candidates/me/profile")) return json(200, profile);
      if (url.endsWith("/me/profile") && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        staffPatches.push(body);
        staff = { ...staff, ...body };
        return json(200, staff);
      }
      if (url.endsWith("/me/profile")) return json(200, staff);
      if (url.endsWith("/me/avatar") && init?.method === "PUT") {
        avatars.push(init.body);
        staff = { ...staff, avatar_url: "/users/u1/avatar?v=abc" };
        return json(200, staff);
      }
      if (url.endsWith("/auth/password/change")) {
        passwords.push(JSON.parse(String(init?.body)));
        return opts.passwordStatus && opts.passwordStatus !== 204 ? json(opts.passwordStatus, { code: "wrong_password", title: "x", status: opts.passwordStatus }) : new Response(null, { status: 204 });
      }
      if (url.endsWith("/companies/me") && init?.method === "PATCH") {
        companyPatches.push(JSON.parse(String(init.body)));
        return json(200, { id: "c1", name: "Ромашка 2", status: "verified", description: null });
      }
      if (url.endsWith("/companies/me")) return json(200, { id: "c1", name: "Ромашка", status: "verified", description: "О нас" });
      if (url.endsWith("/me/consents") && init?.method === "PUT") {
        puts.push(JSON.parse(String(init.body)));
        return json(200, consents(opts.pd));
      }
      if (url.endsWith("/me/consents")) return opts.consentsStatus ? json(opts.consentsStatus, { code: "unavailable" }) : json(200, consents(opts.pd));
      if (url.endsWith("/me/telegram/link")) return json(200, { deep_link: "https://t.me/bot?start=link_x" });
      return json(404);
    }),
  );
  return { visibility, puts, profilePatches, passwords, companyPatches, staffPatches, avatars };
}

function mount(path = "/settings") {
  return render(
    <MemoryRouter initialEntries={[path]}>
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
  mount("/settings?tab=privacy");
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
  mount("/settings?tab=consents");
  expect(await screen.findByTestId("settings-consent-pd_processing")).toBeDisabled();
  expect(screen.getByTestId("settings-consent-pd_processing")).toBeChecked();
  fireEvent.click(screen.getByTestId("settings-consent-profile_publication"));
  await waitFor(() => expect(puts).toContainEqual({ consents: [{ type: "profile_publication", granted: false, version: "v1" }] }));
});

test("уведомления: согласие на Telegram уходит в PUT", async () => {
  const { puts } = install();
  mount("/settings?tab=notifications");
  fireEvent.click(await screen.findByTestId("settings-consent-telegram_notifications"));
  await waitFor(() => expect(puts).toContainEqual({ consents: [{ type: "telegram_notifications", granted: true, version: "v1" }] }));
});

test("уведомления: Telegram привязан — статус, не привязан — кнопка", async () => {
  install({ telegramLinked: true });
  mount("/settings?tab=notifications");
  expect(await screen.findByTestId("settings-telegram-linked")).toHaveTextContent("привязан");
  expect(screen.queryByTestId("settings-telegram-link")).toBeNull();
});

test("уведомления: без привязки есть кнопка", async () => {
  install();
  mount("/settings?tab=notifications");
  expect(await screen.findByTestId("settings-telegram-link")).toBeInTheDocument();
});

test("пустое состояние: нет согласия на ПДн — одна кнопка «Дать согласие»", async () => {
  install({ pd: false });
  mount("/settings?tab=consents");
  expect(await screen.findByText("Согласия не даны — профиль скрыт от компаний")).toBeInTheDocument();
  expect(screen.getByTestId("settings-empty-action")).toHaveAttribute("href", "/consents");
  expect(screen.queryByTestId("privacy-settings")).toBeNull();
});

test("ошибка: «Не загрузилось» с кодом и повтором", async () => {
  install({ consentsStatus: 503 });
  mount("/settings?tab=consents");
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

test("старый /me/settings ведёт на /settings", async () => {
  install();
  mount("/me/settings");
  expect(await screen.findByTestId("settings-profile")).toBeInTheDocument();
});

test("оформление: две темы, выбор сохраняется", async () => {
  install();
  mount("/settings?tab=appearance");
  fireEvent.click(await screen.findByTestId("settings-theme-dark"));
  expect(screen.getByTestId("settings-theme-dark")).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByTestId("settings-theme-light")).toHaveAttribute("aria-pressed", "false");
  expect(localStorage.getItem("fsp-theme")).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
  fireEvent.click(screen.getByTestId("settings-theme-light"));
  expect(document.documentElement.classList.contains("dark")).toBe(false);
});

test("профиль кандидата: ФИО уходит в PATCH, пустое значение очищает", async () => {
  const { profilePatches } = install();
  mount();
  const input = await screen.findByTestId("settings-full-name");
  fireEvent.change(input, { target: { value: "  Анна Смирнова " } });
  fireEvent.submit(screen.getByTestId("settings-profile-form"));
  await waitFor(() => expect(profilePatches).toContainEqual({ full_name: "Анна Смирнова" }));
  expect(await screen.findByTestId("settings-saved")).toBeInTheDocument();
  fireEvent.change(input, { target: { value: "" } });
  fireEvent.submit(screen.getByTestId("settings-profile-form"));
  await waitFor(() => expect(profilePatches).toContainEqual({ full_name: null }));
});

test("вкладки: у кандидата шесть, неизвестная ?tab= открывает профиль", async () => {
  install();
  mount("/settings?tab=nope");
  expect(await screen.findByTestId("settings-profile")).toBeInTheDocument();
  for (const t of ["profile", "privacy", "notifications", "consents", "appearance", "security"]) expect(screen.getByTestId(`settings-tab-${t}`)).toBeInTheDocument();
});

test("работодатель: личный профиль уходит в PATCH /me/profile, компания — ссылкой с ролью (E39-24)", async () => {
  const { staffPatches, companyPatches } = install({ role: "employer", company: true });
  mount();
  const name = await screen.findByTestId("settings-full-name");
  expect(screen.queryByTestId("settings-tab-privacy")).toBeNull();
  await waitFor(() => expect(name).toHaveValue("Анна"));
  fireEvent.change(screen.getByTestId("settings-position"), { target: { value: "HR-партнёр" } });
  fireEvent.change(screen.getByTestId("settings-about"), { target: { value: "**Ищу** бэкендеров" } });
  fireEvent.submit(screen.getByTestId("settings-profile-form"));
  await waitFor(() => expect(staffPatches).toContainEqual({ full_name: "Анна", position: "HR-партнёр", about: "**Ищу** бэкендеров" }));
  expect(await screen.findByTestId("settings-saved")).toBeInTheDocument();
  expect(screen.getByTestId("settings-company-role")).toHaveTextContent("Владелец");
  expect(companyPatches).toEqual([]);
});

test("работодатель: фото уходит в PUT /me/avatar, появляется «Убрать фото»", async () => {
  const { avatars } = install({ role: "employer", company: true });
  mount();
  const input = await screen.findByTestId("settings-avatar-input");
  const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "a.png", { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(avatars).toHaveLength(1));
  expect(avatars[0]).toBeInstanceOf(FormData);
  expect(await screen.findByTestId("settings-avatar-remove")).toBeInTheDocument();
});

test("админ ФСП: профиль, оформление и безопасность", async () => {
  install({ role: "fsp_admin" });
  mount();
  expect(await screen.findByTestId("settings-account-email")).toHaveTextContent("a@b.ru");
  expect(await screen.findByTestId("settings-full-name")).toBeInTheDocument();
  expect(screen.queryByTestId("settings-company")).toBeNull();
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Профиль", "Оформление", "Безопасность"]);
});

test("безопасность: проверка полей и смена пароля", async () => {
  const { passwords } = install();
  mount("/settings?tab=security");
  const submit = await screen.findByTestId("settings-password-submit");
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByTestId("settings-password-current"), { target: { value: "old-password" } });
  fireEvent.change(screen.getByTestId("settings-password-new"), { target: { value: "new-password-1" } });
  fireEvent.change(screen.getByTestId("settings-password-repeat"), { target: { value: "different" } });
  expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByTestId("settings-password-repeat"), { target: { value: "new-password-1" } });
  expect(submit).toBeEnabled();
  fireEvent.click(submit);
  await waitFor(() => expect(passwords).toContainEqual({ current_password: "old-password", new_password: "new-password-1" }));
  expect(await screen.findByTestId("settings-password-message")).toHaveTextContent("Пароль изменён");
  expect(screen.getByTestId("settings-password-current")).toHaveValue("");
});

test("безопасность: неверный текущий пароль — понятная ошибка", async () => {
  install({ passwordStatus: 403 });
  mount("/settings?tab=security");
  fireEvent.change(await screen.findByTestId("settings-password-current"), { target: { value: "bad-password" } });
  fireEvent.change(screen.getByTestId("settings-password-new"), { target: { value: "new-password-1" } });
  fireEvent.change(screen.getByTestId("settings-password-repeat"), { target: { value: "new-password-1" } });
  fireEvent.click(screen.getByTestId("settings-password-submit"));
  expect(await screen.findByTestId("settings-password-message")).toHaveTextContent("Текущий пароль указан неверно");
});
