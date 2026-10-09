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
  logo_key: null,
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
    { user_id: "u2", role: "member", email: "hr@x.io", full_name: "Анна", position: "HR", avatar_url: "/users/u2/avatar?v=1", is_me: role === "member" },
  ],
  invites: role === "admin" ? [{ id: "i1", email: "next@x.io", created_at: "2026-10-01T00:00:00Z", expires_at: "2026-10-08T00:00:00Z" }] : [],
  can_manage: role === "admin",
});

type Opts = { role?: string; me?: "anon" | "employer" | "candidate"; preview?: number; acceptCode?: string };

function install(opts: Opts = {}) {
  const role = opts.role ?? "admin";
  const calls: { method: string; url: string; body?: unknown }[] = [];
  let joined = false;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
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
      if (url.endsWith("/companies/me/invites") && method === "POST") return json(201, { id: "i2", email: "z@x.io", created_at: "2026-10-01T00:00:00Z", expires_at: "2026-10-08T00:00:00Z", url: "http://web/invite/company/tok" });
      if (url.includes("/companies/me/invites/") && method === "DELETE") return new Response(null, { status: 204 });
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

test("владелец: правит компанию с Markdown-описанием, видит приглашения и зовёт HR", async () => {
  const calls = install({ role: "admin" });
  mount("/employer/company");
  const desc = await screen.findByTestId("company-description");
  await waitFor(() => expect(desc).toHaveValue("## О нас\n\n- **Python**"));
  fireEvent.change(desc, { target: { value: "**Новое** описание" } });
  fireEvent.submit(screen.getByTestId("company-form"));
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ name: "Ромашка", description: "**Новое** описание" }));

  expect(await screen.findAllByTestId("company-member")).toHaveLength(2);
  expect(screen.getByTestId("company-invite")).toHaveTextContent("next@x.io");
  expect(screen.getAllByTestId("company-member-remove")).toHaveLength(1); // владельца убрать нельзя
  fireEvent.change(screen.getByTestId("company-invite-email"), { target: { value: "z@x.io" } });
  fireEvent.submit(screen.getByTestId("company-invite-form"));
  expect(await screen.findByTestId("company-invite-link")).toHaveTextContent("http://web/invite/company/tok");
  expect(calls.find((c) => c.url.endsWith("/companies/me/invites"))?.body).toEqual({ email: "z@x.io" });
  fireEvent.click(screen.getByTestId("company-invite-revoke"));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/companies/me/invites/i1"))).toBe(true));
});

test("HR: компания только для чтения, описание отрисовано Markdown, без управления командой", async () => {
  install({ role: "member" });
  mount("/employer/company");
  expect(await screen.findByTestId("company-readonly")).toBeInTheDocument();
  expect(screen.queryByTestId("company-form")).toBeNull();
  const view = screen.getByTestId("company-description-view");
  expect(view.querySelector("h4")).toHaveTextContent("О нас"); // ## → h4 внутри страницы
  expect(view.querySelector("strong")).toHaveTextContent("Python");
  expect(await screen.findAllByTestId("company-member")).toHaveLength(2);
  expect(screen.queryByTestId("company-invite-form")).toBeNull();
  expect(screen.queryByTestId("company-member-remove")).toBeNull();
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
