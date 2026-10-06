import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import RunPage from "@/features/runs/RunPage";
import { getRunId, setRunId } from "@/shared/lib/track";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const RUN_ID = "11111111-1111-4111-8111-111111111111";
const calls: { url: string; method: string; body: unknown }[] = [];
let state: { status: string; tasks: { id: string; title: string; target: number; count: number; done: boolean }[]; all_done: boolean };

beforeEach(() => {
  calls.length = 0;
  setRunId(null);
  state = {
    status: "invited",
    all_done: false,
    tasks: [
      { id: "shortlist", title: "Найти 5 подходящих кандидатов", target: 5, count: 2, done: false },
      { id: "offer_sent", title: "Отправить оффер", target: 1, count: 0, done: false },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/run/tok/start")) {
        state.status = "started";
        return res(200, { id: RUN_ID, scenario: "employer", ...state });
      }
      if (url.endsWith("/run/tok/sus")) {
        state.status = "finished";
        return res(200, { id: RUN_ID, scenario: "employer", ...state });
      }
      if (url.endsWith("/run/tok")) return res(200, { id: RUN_ID, scenario: "employer", ...state });
      return res(404, { code: "not_found" });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(token = "tok") {
  render(
    <MemoryRouter initialEntries={[`/run/${token}`]}>
      <Providers client={makeQueryClient()}>
        <Routes>
          <Route path="/run/:token" element={<RunPage />} />
        </Routes>
      </Providers>
    </MemoryRouter>,
  );
}

test("старт запускает прогон и ставит метку run_id для событий", async () => {
  mount();
  expect(await screen.findByText("2 из 5")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Начать"));
  await screen.findByText("Открыть сервис");
  expect(calls.some((c) => c.url.endsWith("/run/tok/start") && c.method === "POST")).toBe(true);
  expect(getRunId()).toBe(RUN_ID);
});

test("неизвестная ссылка — понятная ошибка", async () => {
  mount("nope");
  expect(await screen.findByText(/Ссылка не подходит/)).toBeInTheDocument();
});

test("анкета SUS: без ответов не уходит, с ответами завершает прогон", async () => {
  state.status = "started";
  mount();
  fireEvent.click(await screen.findByText("Завершить и оценить"));
  fireEvent.click(await screen.findByText("Отправить"));
  expect(await screen.findByText("Ответьте на все десять утверждений.")).toBeInTheDocument();

  for (let i = 1; i <= 10; i++) fireEvent.click(screen.getByLabelText(`${i}: ${i % 2 ? 5 : 1}`));
  fireEvent.click(screen.getByLabelText("Да"));
  fireEvent.click(screen.getByText("Отправить"));

  await screen.findByText(/Ответы получены/);
  const sus = calls.find((c) => c.url.endsWith("/sus"))!;
  expect(sus.body).toEqual({ answers: [5, 1, 5, 1, 5, 1, 5, 1, 5, 1], category_agree: true, notes: null });
  await waitFor(() => expect(getRunId()).toBeNull());
});
