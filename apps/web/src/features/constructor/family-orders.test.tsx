import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

/** E43-9: «Сгенерировать задания» в «Допуске заданий» — форма, заказ, статус и счётчик. */

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];
let orders: Record<string, unknown>[];
let used: number;
let postReply: () => Response;

const order = (over: Record<string, unknown> = {}) => ({
  id: "o1", skill: "sql", kind: "exact", level: 3, count: 3, status: "queued", created: 0, rejected: {}, error: null,
  created_at: "2026-10-10T10:00:00Z", updated_at: "2026-10-10T10:00:00Z", duplicate: false, ...over,
});

beforeEach(() => {
  calls.length = 0;
  orders = [];
  used = 0;
  postReply = () => res(202, order());
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || (url.endsWith("/me") && !url.includes("/companies"))) return res(200, { id: "u1", email: "a@b.ru", role: "fsp_admin", consents: [] });
      if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "sql", name: "SQL", kind: "hard" }, { slug: "python", name: "Python", kind: "hard" }] });
      if (url.includes("/admin/assessment/generate") && method === "POST") return postReply();
      if (url.includes("/admin/assessment/generate")) return res(200, { items: orders, used_today: used, limit: 20, max_count: 10 });
      if (url.includes("/admin/families")) return res(200, []);
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
    <MemoryRouter initialEntries={["/admin/families"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

async function openForm() {
  mount();
  fireEvent.click(await screen.findByTestId("gen-open"));
  return screen.findByTestId("gen-dialog");
}

describe("Сгенерировать задания (E43-9)", () => {
  test("заказ: навык, тип, уровень, количество → POST /admin/assessment/generate", async () => {
    const dialog = await openForm();
    fireEvent.change(within(dialog).getByTestId("gen-skill"), { target: { value: "SQL" } });
    fireEvent.click(await screen.findByRole("option", { name: /SQL/ }));
    fireEvent.click(within(dialog).getByTestId("gen-kind-choice"));
    const count = within(dialog).getByTestId("gen-count");
    fireEvent.change(count, { target: { value: "25" } });
    fireEvent.click(within(dialog).getByTestId("gen-submit"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.includes("/admin/assessment/generate"))).toBe(true));
    const post = calls.find((c) => c.method === "POST" && c.url.includes("/admin/assessment/generate"));
    expect(post?.body).toMatchObject({ skill: "sql", kind: "choice", level: 3 });
    expect((post?.body as { count: number }).count).toBeLessThanOrEqual(10);
    expect(await screen.findByTestId("gen-note")).toHaveTextContent("в очереди");
  });

  test("без навыка запрос не уходит", async () => {
    const dialog = await openForm();
    fireEvent.click(within(dialog).getByTestId("gen-submit"));
    expect(await within(dialog).findByTestId("gen-error")).toHaveTextContent("Выберите навык");
    expect(calls.some((c) => c.method === "POST" && c.url.includes("/admin/assessment"))).toBe(false);
  });

  test("повторный заказ: сообщение «уже в работе»", async () => {
    postReply = () => res(202, order({ duplicate: true }));
    const dialog = await openForm();
    fireEvent.change(within(dialog).getByTestId("gen-skill"), { target: { value: "Python" } });
    fireEvent.click(await screen.findByRole("option", { name: /Python/ }));
    fireEvent.click(within(dialog).getByTestId("gen-submit"));
    expect(await screen.findByTestId("gen-note")).toHaveTextContent("уже в работе");
  });

  test("дневной лимит: кнопка заказа выключена", async () => {
    used = 20;
    const dialog = await openForm();
    expect(await within(dialog).findByTestId("gen-quota")).toHaveTextContent("лимит");
    await waitFor(() => expect(within(dialog).getByTestId("gen-submit")).toBeDisabled());
  });

  test("429 daily_limit: причина в форме", async () => {
    postReply = () => res(429, { code: "daily_limit", status: 429, title: "x", type: "x" });
    const dialog = await openForm();
    fireEvent.change(within(dialog).getByTestId("gen-skill"), { target: { value: "SQL" } });
    fireEvent.click(await screen.findByRole("option", { name: /SQL/ }));
    fireEvent.click(within(dialog).getByTestId("gen-submit"));
    expect(await within(dialog).findByTestId("gen-error")).toHaveTextContent("Дневной лимит");
  });

  test("статусы заказов и счётчик черновиков", async () => {
    used = 3;
    orders = [
      order({ id: "a", status: "running" }),
      order({ id: "b", status: "done", created: 2, rejected: { duplicate: 1 } }),
      order({ id: "c", status: "failed", error: "llm_disabled" }),
    ];
    mount();
    expect(await screen.findByTestId("gen-orders")).toBeInTheDocument();
    expect(screen.getByTestId("gen-orders-quota")).toHaveTextContent("3 из 20");
    expect(screen.getByTestId("gen-status-a")).toHaveTextContent("Идёт");
    expect(screen.getByTestId("gen-status-b")).toHaveTextContent("Готово");
    expect(screen.getByTestId("gen-count-b")).toHaveTextContent("2 из 3 в черновиках");
    expect(screen.getByTestId("gen-count-b")).toHaveTextContent("повтор 1");
    expect(screen.getByTestId("gen-count-c")).toHaveTextContent("Модель выключена");
    fireEvent.click(screen.getByTestId("gen-drafts-b"));
    await waitFor(() => expect(calls.some((c) => c.url.includes("/admin/families?status=draft"))).toBe(true));
  });
});
