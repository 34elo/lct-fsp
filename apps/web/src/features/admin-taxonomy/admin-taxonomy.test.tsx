import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { buildCard, buildWeights, cardErrors, cardToForm, professionErrors, splitLines, weightRows } from "./model";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const problem = (status: number, code: string) => res(status, { code, status, title: "x", type: "x" });
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const calls: { url: string; method: string; body: Record<string, any> }[] = [];
let professions: Record<string, unknown>[];
let postReply: () => Response;
let putReply: () => Response;
let cardSource = "file";

const card = () => ({
  schema_version: 1, skill: "sql", type: "hard", summary: "Пишет запросы и понимает индексы.",
  levels: {
    junior: ["Пишет SELECT с фильтрами", "Делает простые JOIN"],
    middle: ["Читает план запроса", "Подбирает индексы"],
    senior: ["Проектирует схему", "Разбирает блокировки"],
  },
  concepts: [{ term: "Индекс", note: "структура для поиска" }, { term: "План", note: "порядок выполнения" }, { term: "JOIN", note: "соединение таблиц" }],
  misconceptions: [{ claim: "Больше индексов быстрее", truth: "каждый замедляет запись" }, { claim: "NULL равен NULL", truth: "сравнение даёт неизвестно" }],
});

beforeEach(() => {
  calls.length = 0;
  cardSource = "file";
  professions = [{ slug: "backend", title: "Бэкенд", skill_weights: { sql: 0.8, python: 0.6 }, skill_types: {} }];
  postReply = () => res(201, { ...professions[0], slug: "qa", title: "QA" });
  putReply = () => res(200, { skill: "sql", source: "admin", version: 3, card: card(), taxonomy_version: 9 });
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "fsp_admin", consents: ["pd_processing"] });
      if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "sql", name: "SQL", kind: "hard" }, { slug: "python", name: "Python", kind: "hard" }] });
      if (url.endsWith("/admin/professions") && method === "POST") return postReply();
      if (url.includes("/admin/professions/backend") && method === "PATCH") return res(200, professions[0]);
      if (url.includes("/admin/professions/backend") && method === "DELETE") return res(200, { slug: "backend", taxonomy_version: 5 });
      if (url.endsWith("/admin/professions")) return res(200, professions);
      if (url.endsWith("/admin/skill-cards/sql") && method === "PUT") return putReply();
      if (url.endsWith("/admin/skill-cards/sql")) return res(200, { skill: "sql", source: cardSource, version: 2, card: card() });
      if (url.endsWith("/admin/skill-cards")) return res(200, [{ skill: "sql", type: "hard", source: cardSource, version: 2 }]);
      return res(404, { code: "not_found" });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount() {
  render(
    <MemoryRouter initialEntries={["/admin/professions"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}
const type = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });
// Combobox из @fsp/ui: ввод фильтрует список, Enter выбирает первый найденный.
const choose = (id: string, value: string) => {
  type(id, value);
  fireEvent.keyDown(screen.getByTestId(id), { key: "Enter" });
};

describe("model", () => {
  test("веса: запятая, диапазон (0, 1], повтор навыка", () => {
    const rows = (a: [string, string][]) => a.map(([skill, weight], id) => ({ id, skill, weight }));
    expect(buildWeights(rows([["sql", "0,5"]]))).toEqual({ sql: 0.5 });
    expect(professionErrors({ slug: "qa", title: "QA", rows: rows([["sql", "0"]]) }, true).weights).toBeTruthy();
    expect(professionErrors({ slug: "qa", title: "QA", rows: rows([["sql", "1.2"]]) }, true).weights).toBeTruthy();
    expect(professionErrors({ slug: "qa", title: "QA", rows: rows([["sql", "1"]]) }, true)).toEqual({});
    expect(professionErrors({ slug: "Q", title: "QA", rows: rows([["a", "1"], ["a", "1"]]) }, true)).toMatchObject({ slug: expect.any(String), weights: expect.any(String) });
    expect(weightRows({ sql: 0.8 })[0]).toMatchObject({ skill: "sql", weight: "0.8" });
  });
  test("карточка: границы утверждений, понятий, заблуждений, дубли", () => {
    const f = cardToForm(card() as never);
    expect(cardErrors(f)).toEqual({});
    expect(cardErrors({ ...f, levels: { ...f.levels, junior: "Одно" } })["levels-junior"]).toBeTruthy();
    expect(cardErrors({ ...f, levels: { ...f.levels, middle: Array(9).fill(0).map((_, i) => `Утверждение ${i}`).join("\n") } })["levels-middle"]).toBeTruthy();
    expect(cardErrors({ ...f, levels: { ...f.levels, senior: f.levels.junior } }).levels).toBeTruthy();
    expect(cardErrors({ ...f, concepts: f.concepts.slice(0, 2) }).concepts).toBeTruthy();
    expect(cardErrors({ ...f, misconceptions: f.misconceptions.slice(0, 1) }).misconceptions).toBeTruthy();
    expect(buildCard("sql", "hard", f).levels.junior).toEqual(splitLines(f.levels.junior));
  });
});

describe("E13-4a профессии", () => {
  test("скрытая профессия помечена в списке (E36-2)", async () => {
    professions = [...professions, { slug: "ml", title: "ML", skill_weights: { python: 1 }, skill_types: {}, active: false }];
    mount();
    expect(await screen.findByTestId("admin-prof-hidden-ml")).toHaveTextContent("скрыта в опросе");
    expect(screen.queryByTestId("admin-prof-hidden-backend")).toBeNull();
  });

  test("список и правка: PATCH с заменой весов", async () => {
    mount();
    expect(await screen.findByTestId("admin-prof-title-backend")).toHaveTextContent("Бэкенд");
    fireEvent.click(screen.getByTestId("admin-prof-edit-backend"));
    expect(await screen.findByTestId("admin-prof-weight-1")).toHaveValue("0.6");
    type("admin-prof-weight-1", "0,9");
    fireEvent.click(screen.getByTestId("admin-prof-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PATCH")).toBe(true));
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ title: "Бэкенд", skill_weights: { sql: 0.8, python: 0.9 } });
    expect(await screen.findByTestId("admin-prof-notice")).toHaveTextContent("сохранена");
  });

  test("создание: локальная ошибка веса без запроса, затем POST", async () => {
    mount();
    fireEvent.click(await screen.findByTestId("admin-prof-create"));
    type("admin-prof-slug", "qa");
    type("admin-prof-title", "QA");
    choose("admin-prof-skill-0", "sql");
    type("admin-prof-weight-0", "2");
    fireEvent.click(screen.getByTestId("admin-prof-save"));
    expect(await screen.findByTestId("admin-prof-weights-error")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/admin/professions"))).toBe(false);
    type("admin-prof-weight-0", "0.7");
    fireEvent.click(screen.getByTestId("admin-prof-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/admin/professions"))).toBe(true));
    expect(calls.find((c) => c.method === "POST" && c.url.endsWith("/admin/professions"))?.body).toEqual({ slug: "qa", title: "QA", skill_weights: { sql: 0.7 } });
  });

  test.each([
    [409, "profession_exists", "уже есть"],
    [422, "invalid_weight", "вне допустимого"],
    [422, "unknown_skill", "не найден"],
    [422, "missing_skill_types", "шесть типов"],
  ])("ошибка %s %s показана по-русски", async (status, code, text) => {
    postReply = () => problem(status, code);
    mount();
    fireEvent.click(await screen.findByTestId("admin-prof-create"));
    type("admin-prof-slug", "qa");
    type("admin-prof-title", "QA");
    choose("admin-prof-skill-0", "sql");
    fireEvent.click(screen.getByTestId("admin-prof-save"));
    expect(await screen.findByTestId("admin-prof-error")).toHaveTextContent(text);
  });

  test("снятие с теста: подтверждение, затем DELETE", async () => {
    mount();
    fireEvent.click(await screen.findByTestId("admin-prof-edit-backend"));
    fireEvent.click(await screen.findByTestId("admin-prof-retire"));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByTestId("admin-prof-retire-yes"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url.endsWith("/admin/professions/backend"))).toBe(true));
  });
});

describe("E13-4a карточки", () => {
  const openCard = async () => {
    mount();
    fireEvent.click(await screen.findByTestId("admin-taxonomy-tab-cards"));
    fireEvent.click(await screen.findByTestId("admin-card-open-sql"));
    return screen.findByTestId("admin-card-editor");
  };

  test("список с источником, редактор показывает источник и версию", async () => {
    mount();
    fireEvent.click(await screen.findByTestId("admin-taxonomy-tab-cards"));
    expect(await screen.findByTestId("admin-card-meta-sql")).toHaveTextContent("файл справочника");
    fireEvent.click(screen.getByTestId("admin-card-open-sql"));
    const ed = await screen.findByTestId("admin-card-editor");
    expect(within(ed).getByTestId("admin-card-source")).toHaveAttribute("data-source", "file");
    expect(within(ed).getByTestId("admin-card-levels-middle")).toHaveValue("Читает план запроса\nПодбирает индексы");
  });

  test("сохранение: PUT со схемой карточки", async () => {
    await openCard();
    type("admin-card-levels-junior", "Пишет SELECT с фильтрами\nДелает простые JOIN\nГруппирует данные");
    fireEvent.click(screen.getByTestId("admin-card-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const body = calls.find((c) => c.method === "PUT")!.body;
    expect(body).toMatchObject({ schema_version: 1, skill: "sql", type: "hard" });
    expect(body.levels.junior).toHaveLength(3);
    expect(await screen.findByTestId("admin-card-notice")).toHaveTextContent("версия 3");
  });

  test("меньше двух утверждений: ошибка без запроса", async () => {
    await openCard();
    type("admin-card-levels-senior", "Одно утверждение");
    fireEvent.click(screen.getByTestId("admin-card-save"));
    expect(await screen.findByText(/Senior: нужно от 2 до 8/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  test("меньше трёх понятий: ошибка без запроса", async () => {
    await openCard();
    fireEvent.click(screen.getByTestId("admin-card-concept-remove-0"));
    fireEvent.click(screen.getByTestId("admin-card-save"));
    expect(await screen.findByTestId("admin-card-concepts-error")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
  });

  test.each([
    ["card_skill_mismatch", "не совпадает с адресом"],
    ["card_type_mismatch", "не совпадает с типом"],
  ])("422 %s", async (code, text) => {
    putReply = () => problem(422, code);
    await openCard();
    fireEvent.click(screen.getByTestId("admin-card-save"));
    expect(await screen.findByTestId("admin-card-error")).toHaveTextContent(text);
  });
});
