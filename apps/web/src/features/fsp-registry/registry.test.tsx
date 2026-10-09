import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import FspRegistry from "@/features/fsp-registry/FspRegistry";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];

const EVENT = { id: "e-1", title: "Кубок (вымышленный)", discipline: "product", level: "national", date: "2026-05-01", results: 2 };
const REQ = {
  id: "11111111-1111-1111-1111-111111111111",
  candidate_id: "22222222-2222-2222-2222-222222222222",
  full_name: "Чужой Человек",
  email: "other@x.ru",
  phone: null,
  event: "Кубок",
  status: "pending",
  reason: null,
  participant_id: null,
  created_at: "2026-10-09T10:00:00Z",
  decided_at: null,
  candidates: [{ id: "r-1", full_name: "Чужой Человек", email: "other@x.ru", phone: null, linked: false }],
};

beforeEach(() => {
  calls.length = 0;
  setAccessToken("t");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      const path = url.split("?")[0];
      if (path.endsWith("/admin/fsp/events") && method === "GET") return res(200, [EVENT]);
      if (path.endsWith("/admin/fsp/events/e-1")) return res(200, { ...EVENT, ...(calls.at(-1)?.body as object) });
      if (path.endsWith("/admin/fsp/requests")) return res(200, url.includes("status=accepted") ? [] : [REQ]);
      if (path.endsWith("/accept")) return res(200, { ...REQ, status: "accepted", participant_id: "r-1" });
      if (path.endsWith("/reject")) return res(200, { ...REQ, status: "rejected", reason: "Нет в протоколах" });
      if (path.endsWith("/admin/fsp/participants/import"))
        return res(200, { created: 2, updated: 1, errors: [{ line: 4, reason: "bad_email" }] });
      if (path.endsWith("/admin/fsp/participants")) return res(200, []);
      return res(404, { code: "not_found" });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  render(
    <MemoryRouter>
      <Providers client={makeQueryClient()}>
        <FspRegistry />
      </Providers>
    </MemoryRouter>,
  );
}

const openTab = (name: RegExp) => {
  const tab = screen.getByRole("tab", { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
};

test("мероприятие: правка из списка уходит PATCH", async () => {
  mount();
  expect(await screen.findByText("Кубок (вымышленный)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Править" }));
  const title = screen.getByLabelText("Название");
  expect(title).toHaveValue("Кубок (вымышленный)");
  fireEvent.change(title, { target: { value: "Кубок 2026" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ title: "Кубок 2026", discipline: "product", level: "national", date: "2026-05-01" }));
});

test("заявка: подсказка участника и «Принять»", async () => {
  mount();
  await screen.findByRole("tab", { name: /Заявки/ });
  openTab(/Заявки/);
  expect(await screen.findByTestId("fsp-request")).toHaveTextContent("Чужой Человек");
  fireEvent.click(screen.getByRole("button", { name: "Принять" }));
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/accept"))?.body).toEqual({ participant_id: "r-1" }));
});

test("заявка: отказ с причиной", async () => {
  mount();
  await screen.findByRole("tab", { name: /Заявки/ });
  openTab(/Заявки/);
  await screen.findByTestId("fsp-request");
  const reject = screen.getByRole("button", { name: "Отклонить" });
  expect(reject).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Причина отказа"), { target: { value: "Нет в протоколах" } });
  fireEvent.click(reject);
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/reject"))?.body).toEqual({ reason: "Нет в протоколах" }));
});

test("участники: импорт CSV и отчёт об ошибках", async () => {
  mount();
  await screen.findByRole("tab", { name: /Участники/ });
  openTab(/Участники/);
  fireEvent.change(await screen.findByLabelText("Содержимое CSV"), { target: { value: "ФИО;email\nА Б;a@b.ru" } });
  fireEvent.click(screen.getByRole("button", { name: "Загрузить" }));
  expect(await screen.findByText("Добавлено: 2, обновлено: 1.")).toBeInTheDocument();
  expect(screen.getByText(/строка 4: неверный email/)).toBeInTheDocument();
  expect(calls.find((c) => c.url.endsWith("/participants/import"))?.body).toEqual({ csv: "ФИО;email\nА Б;a@b.ru" });
});
