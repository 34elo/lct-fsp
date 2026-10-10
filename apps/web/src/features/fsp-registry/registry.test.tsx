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
      if (path.endsWith("/admin/fsp/events") && method === "POST") return res(201, { ...EVENT, id: "e-2" });
      if (path.endsWith("/admin/fsp/events/e-1")) return res(200, { ...EVENT, ...(calls.at(-1)?.body as object) });
      if (path.endsWith("/admin/fsp/requests")) return res(200, url.includes("status=accepted") ? [] : [REQ]);
      if (path.endsWith("/accept")) return res(200, { ...REQ, status: "accepted", participant_id: "r-1" });
      if (path.endsWith("/reject")) return res(200, { ...REQ, status: "rejected", reason: "Нет в протоколах" });
      if (path.endsWith("/admin/fsp/registry/import")) {
        const b = calls.at(-1)?.body as { commit: boolean };
        const line = (n: number, status: "ok" | "error") => ({ line: n, participant: "p", event: "Кубок", status, action: status === "ok" ? "create" : null, error: status === "error" ? "participant_not_found" : null });
        return res(200, {
          committed: b.commit,
          summary: { total: 2, errors: 1, created: 1, updated: 0, unchanged: 0 },
          new_events: [],
          lines: [line(2, "ok"), line(3, "error")],
        });
      }
      if (path.endsWith("/admin/fsp/participants/import"))
        return res(200, { created: 2, updated: 1, errors: [{ line: 4, reason: "bad_email" }] });
      if (path.endsWith("/admin/fsp/participants") && method === "POST") return res(201, { id: "r-9", full_name: "Иванова Мария", linked: false });
      if (path.endsWith("/admin/fsp/participants")) return res(200, []);
      return res(404, { code: "not_found" });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(entry = "/federation/registry") {
  render(
    <MemoryRouter initialEntries={[entry]}>
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

test("мероприятие: правка из списка в модалке уходит PATCH", async () => {
  mount();
  expect(await screen.findByText("Кубок (вымышленный)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Править" }));
  const title = await screen.findByLabelText("Название");
  expect(title).toHaveValue("Кубок (вымышленный)");
  fireEvent.change(title, { target: { value: "Кубок 2026" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ title: "Кубок 2026", discipline: "product", level: "national", date: "2026-05-01" }));
});

test("реестр — одна страница с четырьмя вкладками и одной кнопкой «Создать» (E41-15)", async () => {
  mount();
  await screen.findByRole("tab", { name: /Участники/ });
  expect(screen.getAllByRole("tab").map((t) => t.textContent?.replace(/\d+$/, ""))).toEqual(["Мероприятия", "Участники", "Результаты", "Заявки"]);
  expect(screen.getAllByRole("button", { name: "Создать" })).toHaveLength(1);
  expect(screen.getByText(/Формат CSV: название; дисциплина/)).toBeInTheDocument();
  expect(screen.getByTestId("page-why")).toHaveTextContent("Мероприятия ФСП");
});

test("«Создать»: выбор, что создаём, и форма участника", async () => {
  mount();
  await screen.findByText("Кубок (вымышленный)");
  fireEvent.click(screen.getByRole("button", { name: "Создать" }));
  const box = await screen.findByTestId("registry-create");
  expect(box).toHaveTextContent("Мероприятие");
  fireEvent.click(screen.getByRole("radio", { name: "Участник" }));
  fireEvent.change(await screen.findByLabelText("ФИО"), { target: { value: "Иванова Мария" } });
  fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/fsp/participants"))?.body).toMatchObject({ full_name: "Иванова Мария" }));
});

test("вкладка «Заявки»: подсказка участника и «Принять»", async () => {
  mount("/federation/registry?tab=requests");
  expect(await screen.findByTestId("fsp-request")).toHaveTextContent("Чужой Человек");
  fireEvent.click(screen.getByRole("button", { name: "Принять" }));
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/accept"))?.body).toEqual({ participant_id: "r-1" }));
});

test("заявка: отказ с причиной", async () => {
  mount("/federation/registry?tab=requests");
  await screen.findByTestId("fsp-request");
  const reject = screen.getByRole("button", { name: "Отклонить" });
  expect(reject).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Причина отказа"), { target: { value: "Нет в протоколах" } });
  fireEvent.click(reject);
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/reject"))?.body).toEqual({ reason: "Нет в протоколах" }));
});

const pickFile = (text: string) => {
  const input = screen.getByLabelText("Импорт CSV") as HTMLInputElement;
  const file = new File([text], "x.csv", { type: "text/csv" });
  Object.defineProperty(file, "text", { value: () => Promise.resolve(text) });
  fireEvent.change(input, { target: { files: [file] } });
};

test("участники: «Импорт CSV» — выбор файла и отчёт об ошибках", async () => {
  mount();
  await screen.findByRole("tab", { name: /Участники/ });
  openTab(/Участники/);
  await screen.findByText("Участников не нашли");
  pickFile("ФИО;email\nА Б;a@b.ru");
  expect(await screen.findByText("Добавлено: 2, обновлено: 1.")).toBeInTheDocument();
  expect(screen.getByText(/строка 4: неверный email/)).toBeInTheDocument();
  expect(calls.find((c) => c.url.endsWith("/participants/import"))?.body).toEqual({ csv: "ФИО;email\nА Б;a@b.ru" });
});

test("мероприятия: «Импорт CSV» создаёт и правит записи, плохие строки в отчёте", async () => {
  mount();
  await screen.findByText("Кубок (вымышленный)");
  pickFile("Название;Дисциплина;Уровень;Дата\nНовый кубок;product;national;01.06.2026\nКубок (вымышленный);Продуктовое программирование;Всероссийский;2026-05-01\nПлохой;nope;national;2026-01-01");
  expect(await screen.findByText("Добавлено: 1, обновлено: 1.")).toBeInTheDocument();
  expect(screen.getByText(/строка 4: неизвестная дисциплина/)).toBeInTheDocument();
  expect(calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/fsp/events"))?.body).toEqual({ title: "Новый кубок", discipline: "product", level: "national", date: "2026-06-01" });
});

test("результаты: «Добавить списком» — превью с ошибками, импорт только после пропуска ошибок (E43-4)", async () => {
  mount("/federation/registry?tab=results");
  fireEvent.click(await screen.findByRole("button", { name: "Добавить списком" }));
  fireEvent.change(await screen.findByLabelText("Или вставьте текст из таблицы"), { target: { value: "p;Кубок;2026-05-01;1\nx;Кубок;2026-05-01;2" } });
  fireEvent.click(screen.getByRole("button", { name: "Проверить" }));
  expect(await screen.findByText(/с ошибками: 1/)).toBeInTheDocument();
  expect(screen.getByText("участника нет в реестре")).toBeInTheDocument();
  const commit = screen.getByRole("button", { name: "Добавить (1)" });
  expect(commit).toBeDisabled();
  fireEvent.click(screen.getByLabelText(/Пропустить строки с ошибками/));
  expect(commit).toBeEnabled();
  fireEvent.click(commit);
  expect(await screen.findByText(/Готово\. Добавлено: 1/)).toBeInTheDocument();
  const sent = calls.filter((c) => c.url.endsWith("/registry/import")).map((c) => c.body);
  expect(sent[0]).toMatchObject({ commit: false });
  expect(sent[1]).toMatchObject({ commit: true, skip_errors: true });
});
