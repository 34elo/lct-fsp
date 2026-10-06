import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { cooldownSeconds } from "@/features/auth/errors";
import { ApiError } from "@/api/mutator";
import { setAccessToken } from "@/shared/lib/token";

const json = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

class FakeES {
  addEventListener() {}
  close() {}
}

function install(opts: { verify?: () => Response; send?: () => Response; verified?: () => boolean }) {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "t" });
      if (url.endsWith("/auth/email/verify")) return opts.verify?.() ?? json(204);
      if (url.endsWith("/auth/email/send")) return opts.send?.() ?? json(204);
      if (url.endsWith("/me")) return json(200, { id: "u1", email: "a@b.ru", role: "candidate", email_verified: opts.verified?.() ?? false, consents: ["pd_processing"] });
      return json(404);
    }),
  );
  return calls;
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/verify-email"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

const typeCode = async (v: string) => fireEvent.change(await screen.findByTestId("verify-code"), { target: { value: v } });

beforeEach(() => {
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("верный код: письмо подтверждено, показан переход дальше", async () => {
  let verified = false;
  const calls = install({ verify: () => ((verified = true), json(204)), verified: () => verified });
  mount();
  await typeCode("123456");
  fireEvent.click(screen.getByTestId("verify-submit"));
  expect(await screen.findByTestId("verify-continue")).toBeInTheDocument();
  expect(calls).toContain("POST /api/v1/auth/email/verify");
});

test.each([
  ["invalid_code", 400, "Неверный код"],
  ["code_expired", 400, "Код истёк"],
  ["too_many_attempts", 429, "Слишком много неверных попыток"],
])("ошибка %s показывается по-русски", async (code, status, text) => {
  install({ verify: () => json(status, { code, status }) });
  mount();
  await typeCode("123456");
  fireEvent.click(screen.getByTestId("verify-submit"));
  expect(await screen.findByTestId("verify-error")).toHaveTextContent(text);
});

test("повторная отправка: после успеха кнопка блокируется на кулдаун", async () => {
  install({});
  mount();
  fireEvent.click(await screen.findByTestId("verify-resend"));
  expect(await screen.findByTestId("verify-info")).toBeInTheDocument();
  expect(screen.getByTestId("verify-resend")).toBeDisabled();
});

test("409 cooldown: кнопка заблокирована по дате из detail, 429 — сообщение про час", async () => {
  const until = new Date(Date.now() + 40_000).toISOString();
  install({ send: () => json(409, { code: "cooldown", detail: until }) });
  mount();
  fireEvent.click(await screen.findByTestId("verify-resend"));
  await waitFor(() => expect(screen.getByTestId("verify-resend")).toBeDisabled());
  expect(screen.getByTestId("verify-error")).toHaveTextContent("подождите");
  expect(screen.getByTestId("verify-resend")).toHaveTextContent(/через \d+ с/);
});

test("429 на отправке: сообщение про лимит", async () => {
  install({ send: () => json(429, { code: "rate_limited" }) });
  mount();
  fireEvent.click(await screen.findByTestId("verify-resend"));
  expect(await screen.findByTestId("verify-error")).toHaveTextContent("через час");
});

test("уже подтверждённая почта не просит код", async () => {
  install({ verified: () => true });
  mount();
  expect(await screen.findByTestId("verify-continue")).toBeInTheDocument();
  expect(screen.queryByTestId("verify-code")).toBeNull();
});

test("cooldownSeconds: без даты — минута, с датой — остаток", () => {
  expect(cooldownSeconds(new ApiError(409, "cooldown", {}))).toBe(60);
  expect(cooldownSeconds(new ApiError(409, "cooldown", { detail: "2026-01-01T00:00:30Z" }), Date.parse("2026-01-01T00:00:00Z"))).toBe(30);
});
