import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { buildSpec, initialForm, localErrors } from "./model";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];
let role = "employer";
let createReply: () => Response;
let queue: Record<string, unknown>[];

const family = (over: Record<string, unknown> = {}) => ({
  id: "f1", slug: "c-abc", kind: "exact", source: "spec", skill_type: "hard", level: 3, b: 0.4, n: 31, anchor: false,
  status: "pilot", key_status: "approved", ai_solvable: 0.2,
  stats: { n: 31, p: 0.5, r_pb: 0.23, seed_spread: 0.11, dif: 0.06, appeals: 0 },
  failed_thresholds: [], log: [{ at: "2026-10-04", from: "draft", to: "pilot", reason: "autocheck" }], spec: { form: { title: "Запросы" } },
  ...over,
});

beforeEach(() => {
  calls.length = 0;
  role = "employer";
  queue = [family()];
  createReply = () =>
    res(201, {
      id: "f9", slug: "c-1", title: "Запросы", kind: "exact", source: "spec", skill: "system_design", skill_type: "hard", level: 3,
      status: "draft", key_status: "approved", form: {}, author_form: {}, key_draft: null, autocheck: { ok: true, seeds: 200 },
      examples: [{ kind: "exact", stem: "Сервис «Заказы» получает 60 запросов", options: [], key: 36000 }],
    });
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || (url.endsWith("/me") && !url.includes("/companies"))) return res(200, { id: "u1", email: "o@b.ru", role, consents: ["pd_processing"] });
      if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "system_design", name: "Проектирование систем", kind: "hard" }] });
      if (url.endsWith("/families") && method === "POST") return createReply();
      if (url.includes("/admin/families/f1/key")) return res(200, family({ key_status: "approved" }));
      if (url.includes("/admin/families/f1/approve")) return res(409, { code: "thresholds_not_met", status: 409, title: "x", type: "x" });
      if (url.includes("/admin/families/f1/pilot")) return res(200, family({ status: "pilot" }));
      if (url.includes("/admin/families")) return res(200, queue);
      return res(404, { code: "not_found" });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

const type = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });

describe("buildSpec", () => {
  test("переменные, ключ exact", () => {
    const f = {
      ...initialForm(),
      title: " Т ", skill: "system_design", stem: "Сколько будет {{rps}}?", answer: "total",
      vars: [
        { id: 1, name: "rps", type: "range" as const, min: "20", max: "200", step: "10", list: "", expr: "" },
        { id: 2, name: "minutes", type: "values" as const, min: "", max: "", step: "", list: "5, 10, x", expr: "" },
        { id: 3, name: "total", type: "expr" as const, min: "", max: "", step: "", list: "", expr: "rps * minutes" },
      ],
    };
    const s = buildSpec(f);
    expect(s.title).toBe("Т");
    expect(s.params).toEqual({ rps: { min: 20, max: 200, step: 10 }, minutes: { values: [5, 10, "x"] } });
    expect(s.derived).toEqual({ total: "rps * minutes" });
    expect(s.answer).toBe("total");
    expect(s.time_limit_s).toBe(90);
  });
  test("choice: номер с 1 → индекс с 0, пустой ключ не уходит", () => {
    const base = { ...initialForm(), kind: "choice" as const, options: "a\nb\n", correct: "2" };
    expect(buildSpec(base).correct).toBe(1);
    expect(buildSpec({ ...base, correct: "" }).correct).toBeUndefined();
  });
  test("sjt: «текст | балл»", () => {
    const s = buildSpec({ ...initialForm(), kind: "sjt", actions: "Откатить | 3\nЖдать" });
    expect(s.actions).toEqual([{ text: "Откатить", score: 3 }, { text: "Ждать" }]);
  });
  test("локальные ошибки", () => {
    expect(Object.keys(localErrors(initialForm()))).toEqual(["title", "skill", "stem"]);
  });
});

describe("K1 конструктор", () => {
  const fill = async () => {
    mount("/employer/families/new");
    await screen.findByTestId("constructor-form");
    type("constructor-title", "Запросы за период");
    type("constructor-skill", "system_design");
    fireEvent.keyDown(screen.getByTestId("constructor-skill"), { key: "Enter" });
    type("constructor-stem", "Сервис получает {{rps}} запросов в секунду");
    type("constructor-answer", "rps");
  };

  test("сохранение: POST /families, превью и автопроверка", async () => {
    await fill();
    fireEvent.click(screen.getByTestId("constructor-save"));
    expect(await screen.findByTestId("constructor-preview")).toBeInTheDocument();
    expect(screen.getByTestId("constructor-autocheck")).toHaveTextContent("200");
    expect(screen.getByTestId("constructor-example-0")).toHaveTextContent("36000");
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/families"));
    expect(post?.body).toMatchObject({ kind: "exact", skill: "system_design", level: 3, answer: "rps" });
  });

  test("пустая форма: локальные ошибки, запроса нет", async () => {
    mount("/employer/families/new");
    fireEvent.click(await screen.findByTestId("constructor-save"));
    expect(await screen.findByText(/Укажите название/)).toBeInTheDocument();
    expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/families"))).toBe(false);
  });

  test("422 autocheck_failed: показывает перечень", async () => {
    createReply = () => res(422, { code: "autocheck_failed", status: 422, title: "x", type: "x", errors: [{ field: "spec", message: "seed 7: деление на ноль" }] });
    await fill();
    fireEvent.click(screen.getByTestId("constructor-save"));
    expect(await screen.findByTestId("constructor-error-code")).toHaveAttribute("data-code", "autocheck_failed");
    expect(screen.getByTestId("constructor-error-details")).toHaveTextContent("деление на ноль");
  });

  test("422 key_required: просит ключ", async () => {
    createReply = () => res(422, { code: "key_required", status: 422, title: "x", type: "x", errors: [{ field: "correct", message: "required" }] });
    await fill();
    fireEvent.click(screen.getByTestId("constructor-save"));
    expect(await screen.findByText(/Укажите правильный ответ/)).toBeInTheDocument();
  });

  test("переключение типа меняет поля ключа, переменные добавляются", async () => {
    mount("/employer/families/new");
    fireEvent.click(await screen.findByTestId("constructor-kind-choice"));
    expect(screen.getByTestId("constructor-options")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("constructor-var-add"));
    expect(screen.getByTestId("constructor-var-1")).toBeInTheDocument();
  });
});

describe("K2 очередь допуска", () => {
  beforeEach(() => {
    role = "fsp_admin";
  });

  test("список с запросом status=pilot и пороги", async () => {
    mount("/admin/families");
    expect(await screen.findByTestId("admission-open-f1")).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("/admin/families?status=pilot"))).toBe(true);
    expect(screen.getByTestId("admission-admit-f1")).toHaveTextContent("пороги");
    fireEvent.click(screen.getByTestId("admission-open-f1"));
    expect(screen.getByTestId("admission-thr-n")).toHaveAttribute("data-failed", "false");
    expect(screen.getByTestId("admission-approve")).toBeEnabled();
  });

  test("пороги не выполнены: допуск закрыт, причины видны", async () => {
    queue = [family({ failed_thresholds: ["n", "dif"], stats: { n: 18, r_pb: 0.14, seed_spread: 0.1, dif: 0.12 }, n: 18 })];
    mount("/admin/families");
    fireEvent.click(await screen.findByTestId("admission-open-f1"));
    expect(screen.getByTestId("admission-approve")).toBeDisabled();
    expect(screen.getByTestId("admission-closed")).toHaveTextContent("n, DIF");
    expect(screen.getByTestId("admission-thr-n")).toHaveAttribute("data-failed", "true");
  });

  test("ключ не утверждён: допуск закрыт, утверждение ключа автора шлёт source", async () => {
    queue = [family({ key_status: "draft", spec: { form: {}, key_draft: { correct: 1 } } })];
    mount("/admin/families");
    fireEvent.click(await screen.findByTestId("admission-open-f1"));
    expect(screen.getByTestId("admission-approve")).toBeDisabled();
    expect(screen.getByTestId("admission-key-draft")).toHaveTextContent("correct");
    fireEvent.click(screen.getByTestId("admission-key-llm"));
    await waitFor(() => expect(calls.find((c) => c.url.includes("/f1/key"))?.body).toEqual({ source: "llm" }));
  });

  test("draft: «В пилот» вызывает /pilot; 409 thresholds_not_met даёт понятный текст", async () => {
    queue = [family({ status: "draft" })];
    mount("/admin/families");
    fireEvent.click(await screen.findByTestId("admission-tab-draft"));
    fireEvent.click(await screen.findByTestId("admission-open-f1"));
    fireEvent.click(screen.getByTestId("admission-pilot"));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/f1/pilot") && c.method === "POST")).toBe(true));
  });

  test("approve при 409 показывает причину", async () => {
    mount("/admin/families");
    fireEvent.click(await screen.findByTestId("admission-open-f1"));
    fireEvent.click(screen.getByTestId("admission-approve"));
    expect(await screen.findByTestId("admission-error")).toHaveTextContent("пороги");
  });

  test("пусто", async () => {
    queue = [];
    mount("/admin/families");
    expect(await screen.findByText("Здесь пусто")).toBeInTheDocument();
  });

  test("чужая роль не попадает в очередь", async () => {
    role = "employer";
    mount("/admin/families");
    await waitFor(() => expect(screen.queryByTestId("admission-page")).not.toBeInTheDocument());
  });
});
