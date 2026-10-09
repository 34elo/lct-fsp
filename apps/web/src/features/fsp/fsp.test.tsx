import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];
let linked = false;
let match: { linked: boolean; matched_by?: string | null; participant_id?: string | null };
let request: Record<string, unknown> | null;
let requestReply: Response | null;

const REQ = {
  id: "11111111-1111-1111-1111-111111111111",
  full_name: "Чужой Человек",
  email: "other@x.ru",
  phone: null,
  event: "Кубок",
  status: "pending",
  reason: null,
  created_at: "2026-10-09T10:00:00Z",
  decided_at: null,
};

beforeEach(() => {
  calls.length = 0;
  linked = false;
  match = { linked: true, matched_by: "email", participant_id: "r-jury" };
  request = null;
  requestReply = null;
  setAccessToken("t");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/candidates/me/fsp"))
        return res(200, {
          link: { linked, verified: linked, participant_id: linked ? "r-jury" : null },
          achievements: linked ? [{ title: "Кубок", place: 2 }] : [],
          ranks: [],
          teams: [],
        });
      if (url.endsWith("/fsp/registry-link")) {
        linked = match.linked;
        return res(200, match);
      }
      if (url.endsWith("/fsp/request")) return res(200, request);
      if (url.endsWith("/fsp/requests")) {
        if (requestReply) return requestReply.clone();
        request = { ...REQ, ...(calls.at(-1)?.body as object) };
        return res(201, request);
      }
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  render(
    <MemoryRouter>
      <Providers client={makeQueryClient()}>
        <FspLinkPanel />
      </Providers>
    </MemoryRouter>,
  );
}

test("одна кнопка: email найден в базе ФСП → привязано", async () => {
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Привязать ФСП" }));
  expect(await screen.findByText(/Ваш email найден в базе ФСП/)).toBeInTheDocument();
  expect(await screen.findByText("ФСП подтверждена")).toBeInTheDocument();
  expect(calls.find((c) => c.url.endsWith("/fsp/registry-link"))?.method).toBe("POST");
  // OAuth и ввод кода из UI убраны
  expect(screen.queryByText("Войти через ФСП")).not.toBeInTheDocument();
  expect(screen.queryByText(/Код из сообщения/)).not.toBeInTheDocument();
});

test("не нашли → заявка → ждёт админа", async () => {
  match = { linked: false };
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Привязать ФСП" }));
  expect(await screen.findByText(/Ваших контактов нет в базе ФСП/)).toBeInTheDocument();
  const send = screen.getByRole("button", { name: "Отправить заявку" });
  expect(send).toBeDisabled();
  fireEvent.change(screen.getByLabelText("ФИО, как в протоколах ФСП"), { target: { value: "Чужой Человек" } });
  fireEvent.change(screen.getByLabelText("Email, под которым вы участвовали"), { target: { value: "other@x.ru" } });
  fireEvent.change(screen.getByLabelText("Мероприятие ФСП"), { target: { value: "Кубок" } });
  fireEvent.click(send);
  await waitFor(() =>
    expect(calls.find((c) => c.url.endsWith("/fsp/requests"))?.body).toEqual({
      full_name: "Чужой Человек",
      email: "other@x.ru",
      phone: null,
      event: "Кубок",
    }),
  );
  expect(await screen.findByTestId("fsp-request-pending")).toHaveTextContent("Админ ФСП проверит");
});

test("ошибка заявки показывается по-русски", async () => {
  match = { linked: false };
  requestReply = res(422, { code: "bad_phone" });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Привязать ФСП" }));
  fireEvent.change(await screen.findByLabelText("ФИО, как в протоколах ФСП"), { target: { value: "Имя Фамилия" } });
  fireEvent.change(screen.getByLabelText("Телефон, под которым вы участвовали"), { target: { value: "12" } });
  fireEvent.click(screen.getByRole("button", { name: "Отправить заявку" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Проверьте телефон");
});

test("отклонённая заявка: причина и повторная подача", async () => {
  request = { ...REQ, status: "rejected", reason: "Нет в протоколах" };
  mount();
  expect(await screen.findByTestId("fsp-request-rejected")).toHaveTextContent("Нет в протоколах");
  fireEvent.click(screen.getByText("Подать заявку заново"));
  expect(screen.getByLabelText("ФИО, как в протоколах ФСП")).toHaveValue("Чужой Человек");
});
