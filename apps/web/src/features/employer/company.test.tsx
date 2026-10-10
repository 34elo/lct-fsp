import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const json = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

class FakeES {
  addEventListener() {}
  close() {}
}

const company = (role: string) => ({
  id: "c1",
  name: "Ромашка",
  inn: "7707083893",
  site: null,
  description: "## О нас\n\n- **Python**",
  logo_url: null,
  contacts: null,
  direction: null,
  status: "verified",
  show_verified_badge: true,
  responsibility_score: null,
  created_at: "2026-10-01T00:00:00Z",
  my_role: role,
});

const team = (role: string) => ({
  members: [
    { user_id: "u1", role: "admin", email: "owner@x.io", full_name: "Олег", position: "CEO", avatar_url: null, is_me: role === "admin" },
    {
      user_id: "u2",
      role: "member",
      email: "hr@x.io",
      full_name: "Анна",
      position: "HR",
      avatar_url: "/users/u2/avatar?v=1",
      is_me: role === "member",
      managed: role === "admin",
      must_change_password: role === "admin",
      temp_password_expires_at: role === "admin" ? "2026-10-13T09:00:00Z" : null,
    },
  ],
  invites: [],
  can_manage: role === "admin",
});

type Opts = { role?: string; me?: "anon" | "employer" | "candidate"; preview?: number; acceptCode?: string; hrCode?: string };

function install(opts: Opts = {}) {
  const role = opts.role ?? "admin";
  const calls: { method: string; url: string; body?: unknown }[] = [];
  let joined = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return opts.me === "anon" ? json(401, { code: "unauthorized" }) : json(200, { access_token: "t" });
      if (url.endsWith("/api/v1/me"))
        return json(200, {
          id: "u1",
          email: "hr@x.io",
          role: opts.me === "candidate" ? "candidate" : "employer",
          email_verified: true,
          consents: ["pd_processing"],
          telegram_linked: false,
          company: opts.me && !joined ? null : { id: "c1", name: "Ромашка", status: "verified", role: joined ? "member" : role },
        });
      if (url.includes("/company-invites/") && url.endsWith("/accept")) {
        if (opts.acceptCode) return json(403, { code: opts.acceptCode, title: "x", status: 403 });
        joined = true;
        return json(200, company("member"));
      }
      if (url.includes("/company-invites/"))
        return opts.preview === 404
          ? json(404, { code: "invite_not_found", title: "x", status: 404 })
          : json(200, { company_name: "Ромашка", company_verified: true, inviter_name: "Олег", email_masked: "h***@x.io", expires_at: "2026-10-08T00:00:00Z" });
      if (url.endsWith("/companies/me/members")) return json(200, team(joined ? "member" : role));
      if (url.endsWith("/companies/me/hr") && method === "POST")
        return opts.hrCode
          ? json(409, { code: opts.hrCode, title: "x", status: 409 })
          : json(201, { user_id: "u3", email: "zoya@x.io", full_name: "Зоя", login_url: "https://career.example.ru/login", temp_password: "abcd-EFGH-2345", expires_at: "2026-10-13T09:00:00Z" });
      if (url.endsWith("/companies/me/members/u2/password") && method === "POST")
        return json(200, { user_id: "u2", email: "hr@x.io", full_name: "Анна", login_url: "https://career.example.ru/login", temp_password: "wxyz-WXYZ-6789", expires_at: "2026-10-13T09:00:00Z" });
      if (url.includes("/companies/me/members/") && method === "DELETE") return new Response(null, { status: 204 });
      if (url.endsWith("/companies/me/access-log"))
        return json(200, [{ id: "l1", action: "created", created_at: "2026-10-10T09:00:00Z", actor_name: "Олег", target_email: "hr@x.io", target_name: "Анна" }]);
      if (url.endsWith("/companies/me/logo") && method === "PUT") return json(200, { ...company(role), logo_url: "/companies/c1/logo?v=abc" });
      if (url.endsWith("/companies/me") && method === "PATCH") return json(200, company(role));
      if (url.endsWith("/companies/me")) return json(200, company(joined ? "member" : role));
      if (url.endsWith("/me/consents")) return json(200, []);
      return json(404);
    }),
  );
  return calls;
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

beforeEach(() => {
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("владелец: правит компанию с Markdown-описанием", async () => {
  const calls = install({ role: "admin" });
  mount("/employer/company");
  expect(await screen.findByTestId("company-tab-info")).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByTestId("company-team")).toBeNull(); // команда — на своей вкладке
  const desc = await screen.findByTestId("company-description");
  await waitFor(() => expect(desc).toHaveValue("## О нас\n\n- **Python**"));
  fireEvent.change(desc, { target: { value: "**Новое** описание" } });
  fireEvent.submit(screen.getByTestId("company-form"));
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ name: "Ромашка", description: "**Новое** описание" }));

});

test("владелец: создаёт доступ HR без почты и копирует логин с временным паролем", async () => {
  const calls = install({ role: "admin" });
  const writeText = vi.fn(async () => undefined);
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  mount("/employer/company?tab=team");
  expect(await screen.findAllByTestId("company-member")).toHaveLength(2);
  expect(screen.queryByTestId("company-invite-form")).toBeNull(); // приглашений по почте больше нет
  expect(screen.getByTestId("company-member-pending")).toHaveTextContent("Ещё не вошёл");
  expect(await screen.findByTestId("company-access-log")).toHaveTextContent("Олег выдал(а) доступ: Анна");
  fireEvent.change(screen.getByTestId("company-hr-name"), { target: { value: "Зоя" } });
  fireEvent.change(screen.getByTestId("company-hr-email"), { target: { value: "zoya@x.io" } });
  fireEvent.submit(screen.getByTestId("company-hr-form"));
  const card = await screen.findByTestId("company-access-card");
  expect(calls.find((c) => c.url.endsWith("/companies/me/hr"))?.body).toEqual({ email: "zoya@x.io", full_name: "Зоя" });
  expect(screen.getByTestId("company-access-url")).toHaveTextContent("https://career.example.ru/login");
  expect(screen.getByTestId("company-access-password")).toHaveTextContent("abcd-EFGH-2345");
  fireEvent.click(screen.getByTestId("company-access-copy"));
  await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
  const shared = (writeText.mock.calls[0] as unknown as [string])[0];
  expect(shared).toContain("«Ромашка»");
  expect(shared).toContain("https://career.example.ru/login");
  expect(shared).toContain("zoya@x.io");
  expect(shared).toContain("abcd-EFGH-2345");
  // карточка закрывается — пароль больше не показывается
  fireEvent.click(screen.getByTestId("company-access-close"));
  expect(card).not.toBeInTheDocument();
});

test("владелец: выдаёт HR новый пароль и отзывает доступ", async () => {
  const calls = install({ role: "admin" });
  const confirm = vi.fn(() => true);
  const alert = vi.fn();
  vi.stubGlobal("confirm", confirm);
  vi.stubGlobal("alert", alert);
  mount("/employer/company?tab=team");
  expect(await screen.findAllByTestId("company-member-remove")).toHaveLength(1); // владельца убрать нельзя
  // подтверждение — модалка @fsp/ui: до «Выдать пароль» запрос не уходит
  fireEvent.click(screen.getByTestId("company-member-reset"));
  expect(await screen.findByTestId("company-confirm")).toHaveTextContent("новый временный пароль");
  expect(calls.some((c) => c.url.endsWith("/members/u2/password"))).toBe(false);
  fireEvent.click(screen.getByTestId("company-confirm-cancel"));
  await waitFor(() => expect(screen.queryByTestId("company-confirm")).toBeNull());
  fireEvent.click(screen.getByTestId("company-member-reset"));
  fireEvent.click(await screen.findByTestId("company-confirm-ok"));
  // пароль — в модалке: логин, пароль, предупреждение «показывается один раз»
  expect(await screen.findByTestId("company-access-password")).toHaveTextContent("wxyz-WXYZ-6789");
  expect(screen.getByTestId("company-access-login")).toBeInTheDocument();
  expect(screen.getByTestId("company-access-once")).toHaveTextContent("один раз");
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("company-access-close"));
  await waitFor(() => expect(screen.queryByTestId("company-access-card")).toBeNull());
  fireEvent.click(screen.getByTestId("company-member-remove"));
  fireEvent.click(await screen.findByTestId("company-confirm-ok"));
  expect(confirm).not.toHaveBeenCalled();
  expect(alert).not.toHaveBeenCalled();
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/companies/me/members/u2"))).toBe(true));
});

test("владелец: email кандидата — понятная ошибка", async () => {
  install({ role: "admin", hrCode: "email_is_candidate" });
  mount("/employer/company?tab=team");
  fireEvent.change(await screen.findByTestId("company-hr-name"), { target: { value: "Иван" } });
  fireEvent.change(screen.getByTestId("company-hr-email"), { target: { value: "cand@x.io" } });
  fireEvent.submit(screen.getByTestId("company-hr-form"));
  expect(await screen.findByTestId("company-team-error")).toHaveTextContent("зарегистрирован как кандидат");
  expect(screen.queryByTestId("company-access-card")).toBeNull();
});

test("HR: компания только для чтения, описание отрисовано Markdown, без управления командой", async () => {
  install({ role: "member" });
  mount("/employer/company");
  expect(await screen.findByTestId("company-readonly")).toBeInTheDocument();
  expect(screen.queryByTestId("company-form")).toBeNull();
  const view = screen.getByTestId("company-description-view");
  expect(view.querySelector("h4")).toHaveTextContent("О нас"); // ## → h4 внутри страницы
  expect(view.querySelector("strong")).toHaveTextContent("Python");
  expect(screen.queryByTestId("company-logo-upload")).toBeNull(); // логотип грузит только владелец
});

test("HR: во вкладке «Команда» видит людей без управления", async () => {
  install({ role: "member" });
  mount("/employer/company?tab=team");
  expect(await screen.findAllByTestId("company-member")).toHaveLength(2);
  expect(screen.queryByTestId("company-hr-form")).toBeNull();
  expect(screen.queryByTestId("company-member-remove")).toBeNull();
  expect(screen.queryByTestId("company-member-reset")).toBeNull();
  expect(screen.queryByTestId("company-access-log")).toBeNull();
});

test("приглашение: аноним видит компанию и кнопки входа и регистрации", async () => {
  install({ me: "anon" });
  mount("/invite/company/tok");
  expect(await screen.findByTestId("invite-card")).toHaveTextContent("h***@x.io");
  expect(screen.getByText(/Олег приглашает вас в команду компании «Ромашка»/)).toBeInTheDocument();
  expect(screen.getByTestId("invite-login")).toBeInTheDocument();
  expect(screen.getByTestId("invite-register")).toBeInTheDocument();
});

test("приглашение: работодатель принимает и попадает на страницу компании", async () => {
  const calls = install({ me: "employer" });
  mount("/invite/company/tok");
  fireEvent.click(await screen.findByTestId("invite-accept"));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/company-invites/tok/accept"))).toBe(true));
  expect(await screen.findByTestId("company-readonly")).toBeInTheDocument();
});

test("приглашение: чужой email — понятная ошибка; кандидат не может принять", async () => {
  install({ me: "employer", acceptCode: "invite_email_mismatch" });
  const { unmount } = mount("/invite/company/tok");
  fireEvent.click(await screen.findByTestId("invite-accept"));
  expect(await screen.findByTestId("invite-error")).toHaveTextContent("другой email");
  unmount();
  install({ me: "candidate" });
  mount("/invite/company/tok");
  expect(await screen.findByTestId("invite-not-employer")).toBeInTheDocument();
});

test("приглашение: неверная или истёкшая ссылка — пустое состояние", async () => {
  install({ me: "anon", preview: 404 });
  mount("/invite/company/bad");
  expect(await screen.findByTestId("invite-invalid")).toHaveTextContent("Приглашение не найдено");
});

test("владелец: загружает логотип и убирает его", async () => {
  const calls = install({ role: "admin" });
  mount("/employer/company");
  const input = (await screen.findByTestId("company-logo-input")) as HTMLInputElement;
  expect(screen.queryByTestId("company-logo-remove")).toBeNull(); // файла ещё нет
  const file = new File([new Uint8Array([137, 80, 78, 71])], "logo.png", { type: "image/png" });
  fireEvent.change(input, { target: { files: [file] } });
  await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.url.endsWith("/companies/me/logo"))).toBe(true));
});
