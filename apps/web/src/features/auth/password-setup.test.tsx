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

/** HR вошёл временным паролем от владельца: до своего пароля другие экраны закрыты. */
function install(opts: { initialCode?: string } = {}) {
  const calls: { method: string; url: string; body?: unknown }[] = [];
  let pending = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ method, url, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "t" });
      if (url.endsWith("/auth/password/initial")) {
        if (opts.initialCode) return json(opts.initialCode === "temp_password_expired" ? 403 : 422, { code: opts.initialCode, title: "x", status: 422 });
        pending = false;
        return new Response(null, { status: 204 });
      }
      if (url.endsWith("/api/v1/me"))
        return json(200, {
          id: "u2",
          email: "hr@x.io",
          role: "employer",
          email_verified: true,
          must_change_password: pending,
          consents: ["pd_processing"],
          telegram_linked: false,
          company: { id: "c1", name: "Ромашка", status: "verified", role: "member" },
        });
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

test("временный пароль: кабинет закрыт до смены, после смены — дальше", async () => {
  const calls = install();
  mount("/employer/company");
  const form = await screen.findByTestId("password-setup-form");
  expect(calls.some((c) => c.url.includes("/companies/"))).toBe(false); // кабинет не грузился
  const submit = screen.getByTestId("password-setup-submit");
  fireEvent.change(screen.getByTestId("password-setup-new"), { target: { value: "my-secret-1" } });
  fireEvent.change(screen.getByTestId("password-setup-repeat"), { target: { value: "my-secret-2" } });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByTestId("password-setup-repeat"), { target: { value: "my-secret-1" } });
  fireEvent.submit(form);
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/auth/password/initial"))?.body).toEqual({ new_password: "my-secret-1" }));
  await waitFor(() => expect(screen.queryByTestId("password-setup-form")).toBeNull());
});

test("временный пароль истёк — понятная ошибка", async () => {
  install({ initialCode: "temp_password_expired" });
  mount("/password/new");
  fireEvent.change(await screen.findByTestId("password-setup-new"), { target: { value: "my-secret-1" } });
  fireEvent.change(screen.getByTestId("password-setup-repeat"), { target: { value: "my-secret-1" } });
  fireEvent.submit(screen.getByTestId("password-setup-form"));
  expect(await screen.findByTestId("password-setup-error")).toHaveTextContent("Попросите владельца");
});
