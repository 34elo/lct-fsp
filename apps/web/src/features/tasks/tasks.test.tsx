import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { candStatus, initialAnswer, isReady, moveItem, toAnswer } from "./model";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const future = "2099-01-01T00:00:00Z";
const base = { profession: "backend", grade: "middle", round: 2, answer_until: future };
let list: unknown[] = [];
let listFail = false;
let role = "candidate";
const fam = { kind: "exact", skill: "sql", level: 3, status: "draft", company_id: "c1" };
let fams: Record<string, unknown>[] = [];
const calls: string[] = [];

const exact = { id: "t1", title: "Запросов за период", kind: "exact", submitted: false, ...base };
const detail = { ...exact, item: { kind: "exact", stem: "Сколько запросов за 10 минут?", options: null } };
const empTasks = [
  { id: "e1", family_id: "f", title: "Ревью миграции", profession: "backend", grade: "middle", kind: "open", period_days: 7, status: "open", round: 1, submissions: 1, scored: 0, rubric: ["Есть откат", "Нет блокировок"] },
  { id: "e2", family_id: "f", title: "Черновик", profession: "backend", grade: "middle", kind: "exact", period_days: 7, status: "draft", round: 1 },
];
const subs = [{ id: "s1", pseudo_id: "abcdef123", round: 1, answer: "добавил откат", score: null, created_at: "2026-10-05T10:00:00Z", invite_url: "/employer/offers/new?candidate=abcdef123&source=regular_task" }];

beforeEach(() => {
  setAccessToken(null);
  calls.length = 0;
  list = [exact];
  listFail = false;
  fams = [
    { ...fam, id: "f-r", title: "Готовое задание", ready: true },
    { ...fam, id: "f-d", title: "Задание в работе", ready: false },
  ];
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role, consents: ["pd_processing"] });
      if (url.includes("/assessment/tasks/t1/answer")) {
        calls.push(String(init?.body));
        return res(200, { ...detail, submitted: true });
      }
      if (url.includes("/assessment/tasks/t1")) return res(200, detail);
      if (url.includes("/assessment/tasks")) return listFail ? res(500, { code: "x" }) : res(200, list);
      if (url.includes("/families/f-d/ready")) {
        calls.push(`ready:${String(init?.body)}`);
        fams = fams.map((f) => (f.id === "f-d" ? { ...f, ready: true } : f));
        return res(200, fams.find((f) => f.id === "f-d"));
      }
      if (url.endsWith("/families")) return res(200, fams);
      if (url.includes("/employer/tasks/e1/submissions/s1/score")) {
        calls.push(String(init?.body));
        return res(200, subs[0]);
      }
      if (url.includes("/employer/tasks/e1/submissions")) return res(200, subs);
      if (url.includes("/employer/tasks/e2/publish")) {
        calls.push("publish");
        return res(200, { ...empTasks[1], delivered: true });
      }
      if (url.includes("/employer/tasks")) return res(200, empTasks);
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

test("модель: ответы по типам и статусы", () => {
  expect(toAnswer({ kind: "exact" }, " 1,5 ")).toBe(1.5);
  expect(toAnswer({ kind: "exact" }, "abc")).toBe("abc");
  expect(toAnswer({ kind: "find_bug" }, [3, 1])).toEqual([1, 3]);
  expect(initialAnswer({ kind: "order", options: ["a", "b", "c"] })).toEqual([0, 1, 2]);
  expect(moveItem([0, 1, 2], 0, 1)).toEqual([1, 0, 2]);
  expect(moveItem([0, 1, 2], 0, -1)).toEqual([0, 1, 2]);
  expect(isReady({ kind: "choice" }, null)).toBe(false);
  expect(isReady({ kind: "choice" }, 0)).toBe(true);
  const chain = { kind: "chain", steps: [{ kind: "choice" }, { kind: "exact" }] };
  expect(isReady(chain, [0, ""])).toBe(false);
  expect(toAnswer(chain, [1, "7"])).toEqual([1, 7]);
  expect(candStatus({ id: "x", kind: "open", submitted: true })).toBe("waiting");
  expect(candStatus({ id: "x", kind: "exact", submitted: true, score: 0.8 })).toBe("scored");
  expect(candStatus({ id: "x", kind: "exact", answer_until: "2000-01-01T00:00:00Z" })).toBe("closed");
});

test("кандидат: список, ответ отправляется числом", async () => {
  mount("/me/tasks");
  expect(await screen.findByText("Запросов за период")).toBeInTheDocument();
  expect(screen.getByTestId("tasks-status")).toHaveTextContent("новое");
  fireEvent.click(screen.getByTestId("tasks-open"));
  expect(await screen.findByTestId("tasks-stem")).toHaveTextContent("10 минут");
  const submit = screen.getByTestId("tasks-submit");
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByTestId("tasks-answer-input"), { target: { value: "36000" } });
  fireEvent.click(submit);
  await waitFor(() => expect(calls).toEqual([JSON.stringify({ answer: 36000 })]));
});

test("кандидат: пусто и ошибка загрузки", async () => {
  list = [];
  mount("/me/tasks");
  expect(await screen.findByTestId("tasks-empty")).toHaveTextContent("Заданий пока нет");
  expect(screen.getByRole("link", { name: "Открыть согласия" })).toHaveAttribute("href", "/consents");
});

test("кандидат: ошибка списка с повтором", async () => {
  listFail = true;
  mount("/me/tasks");
  expect(await screen.findByText(/Не загрузились задания/, undefined, { timeout: 5000 })).toBeInTheDocument();
});

test("работодатель: ответы, оценка рубрикой, «Пригласить», публикация", async () => {
  role = "employer";
  mount("/employer/tasks");
  expect(await screen.findByText("Ревью миграции")).toBeInTheDocument();
  fireEvent.click(screen.getAllByTestId("tasks-toggle")[0]!);
  const invite = await screen.findByTestId("tasks-invite");
  expect(invite).toHaveAttribute("href", "/employer/offers/new?candidate=abcdef123&source=regular_task");
  expect(screen.getByText(/Кандидат abcdef/)).toBeInTheDocument();
  const rubric = await screen.findByTestId("tasks-rubric");
  fireEvent.click(rubric.querySelectorAll("input")[0]!);
  fireEvent.click(screen.getByTestId("tasks-score-save"));
  await waitFor(() => expect(calls).toContain(JSON.stringify({ marks: [true, false] })));
  fireEvent.click(screen.getByTestId("tasks-publish"));
  await waitFor(() => expect(calls).toContain("publish"));
  role = "candidate";
});

test("работодатель: вкладки «Готовые» и «Черновики», «Готово» переносит задание", async () => {
  role = "employer";
  mount("/employer/tasks");
  expect(await screen.findByText("Задание в работе")).toBeInTheDocument(); // есть черновик — он открыт первым
  expect(screen.queryByText("Готовое задание")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("tasks-family-ready"));
  await waitFor(() => expect(calls).toContain(`ready:${JSON.stringify({ ready: true })}`));
  fireEvent.click(screen.getByTestId("tasks-fam-tab-ready"));
  expect(await screen.findByText("Задание в работе")).toBeInTheDocument();
  expect(screen.getByText("Готовое задание")).toBeInTheDocument();
  role = "candidate";
});
