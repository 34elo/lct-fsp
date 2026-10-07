import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const professions = {
  professions: [
    { slug: "backend", title: "Backend-разработчик", skill_weights: {}, skill_types: {} },
    { slug: "frontend", title: "Frontend-разработчик", skill_weights: {}, skill_types: {} },
  ],
  skill_types: [],
  grades: [],
};
const survey = {
  id: null,
  industry: "Электронная коммерция",
  profession: "backend",
  stack: ["python", "fastapi"],
  formats: ["remote"],
  salary_from: 200000,
  salary_to: 260000,
  declared_grade: "middle",
  prefilled: true,
};
const attemptBase = {
  id: "a1",
  profession: "backend",
  declared_grade: "middle",
  stage: "main",
  status: "active",
  answered: 3,
  target: 10,
  started_at: "2026-10-06T09:00:00Z",
  finished_at: null,
};
const finished = {
  ...attemptBase,
  status: "passed",
  answered: 10,
  finished_at: "2026-10-06T09:20:00Z",
  invited_grade: "senior",
  invite_expires_at: "2999-11-05T09:20:00Z",
  invite_attempt_id: null,
  result: {
    grade: "middle",
    theta: 0.4,
    integrity: 0.92,
    needs_confirmation: false,
    by_skill: [
      { skill: "python", items: 6, share: 0.83 },
      { skill: "system_design", items: 4, share: 0.5 },
    ],
    answers: [
      { response_id: "r1", seq: 1, skill: "python", score: 1 },
      { response_id: "r2", seq: 2, skill: "system_design", score: 0 },
    ],
  },
};

type Handler = (url: string, init?: RequestInit) => Response | undefined;

function mount(path: string, handler: Handler) {
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  const calls: { url: string; method: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.endsWith("/taxonomy/professions")) return res(200, professions);
      return handler(url, init) ?? res(404, { code: "not_found" });
    }),
  );
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </Providers>,
  );
  return calls;
}

const tid = (id: string) => screen.findByTestId(id);

describe("опрос (S1)", () => {
  it("предзаполняет, сохраняет опрос и начинает тест", async () => {
    const calls = mount("/me/assessment", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, survey);
      if (url.endsWith("/assessment/survey")) return res(200, { ...survey, id: "s1", prefilled: false });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [] });
      if (url.endsWith("/assessment/attempts") && init?.method === "POST") return res(201, attemptBase);
      if (url.includes("/attempts/a1/next")) return res(200, { done: false, response_id: "r1", seq: 4, kind: "exact", stem: "Что выведет?", time_limit_s: 120 });
      if (url.endsWith("/attempts/a1")) return res(200, attemptBase);
    });
    expect(await tid("assessment-prefilled")).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-industry")).toBeNull(); // ADR-025 п.4: отрасль не спрашиваем
    expect(screen.getByTestId("assessment-profession-backend")).toBeChecked();
    expect(screen.getByTestId("assessment-grade-middle")).toBeChecked();
    fireEvent.change(screen.getByTestId("assessment-stack-input"), { target: { value: "Redis" } });
    fireEvent.click(screen.getByTestId("assessment-stack-add"));
    expect(within(screen.getByTestId("assessment-stack")).getByText(/redis/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("assessment-start"));
    expect(await tid("assessment-item")).toBeInTheDocument();
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body).toMatchObject({ industry: "Электронная коммерция", profession: "backend", declared_grade: "middle", stack: ["python", "fastapi", "redis"], salary_from: 200000 });
    expect(calls.find((c) => c.url.endsWith("/assessment/attempts") && c.method === "POST")!.body).toEqual({ profession: "backend", declared_grade: "middle" });
  });

  it("экспресс-режим (E32-4a): ?mode=express включает переключатель, попытка создаётся с mode", async () => {
    const calls = mount("/me/assessment?mode=express", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, survey);
      if (url.endsWith("/assessment/survey")) return res(200, { ...survey, id: "s1", prefilled: false });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [] });
      if (url.endsWith("/assessment/attempts") && init?.method === "POST") return res(201, { ...attemptBase, mode: "express", target: 6 });
      if (url.includes("/attempts/a1/next")) return res(200, { done: false, response_id: "r1", seq: 1, kind: "exact", stem: "Что выведет?", time_limit_s: 120 });
      if (url.endsWith("/attempts/a1")) return res(200, { ...attemptBase, mode: "express", target: 6 });
    });
    expect(await tid("assessment-express-toggle")).toBeChecked();
    fireEvent.click(screen.getByTestId("assessment-start"));
    expect(await tid("assessment-range")).toHaveTextContent("от 6 до 8");
    expect(calls.find((c) => c.url.endsWith("/assessment/attempts") && c.method === "POST")!.body).toEqual({
      profession: "backend",
      declared_grade: "middle",
      mode: "express",
    });
  });

  it("без грейда тест не начинается, перевёрнутая вилка блокирует сохранение", async () => {
    const calls = mount("/me/assessment", (url) => (url.endsWith("/assessment/survey") ? res(200, { ...survey, declared_grade: null }) : undefined));
    await tid("assessment-survey");
    fireEvent.click(screen.getByTestId("assessment-start"));
    expect(await tid("assessment-need-grade")).toBeInTheDocument();
    expect(calls.some((c) => c.method === "PUT")).toBe(false);
    fireEvent.change(screen.getByTestId("assessment-salary-from"), { target: { value: "300000" } });
    expect(screen.getByText(/не может быть больше/)).toBeInTheDocument();
  });

  it("409 cooldown показывает дату, 403 email_not_verified ведёт на /verify-email", async () => {
    let code = "cooldown";
    mount("/me/assessment", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, survey);
      if (url.endsWith("/assessment/survey")) return res(200, survey);
      if (url.endsWith("/assessment/attempts"))
        return code === "cooldown"
          ? res(409, { code: "cooldown", detail: "2026-11-04T10:00:00+00:00 смена грейда не чаще раза в 90 дней" })
          : res(403, { code: "email_not_verified" });
    });
    await tid("assessment-survey");
    fireEvent.click(screen.getByTestId("assessment-start"));
    const err = await tid("assessment-start-error");
    expect(err).toHaveTextContent("04.11.2026");
    expect(err).toHaveAttribute("data-code", "cooldown");
    code = "email";
    fireEvent.click(screen.getByTestId("assessment-start"));
    await waitFor(() => expect(screen.getByTestId("assessment-start-error")).toHaveAttribute("data-code", "email_not_verified"));
    expect(within(screen.getByTestId("assessment-start-error")).getByRole("link")).toHaveAttribute("href", "/verify-email");
  });
});

describe("опрос (S1) · состояния макета v2", () => {
  const surveyGet = (url: string, init?: RequestInit) => (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET" ? res(200, survey) : undefined);

  it("кулдаун: плашка с датой, грейд в контуре, старт предлагает грейд ниже", async () => {
    const calls = mount("/me/assessment", (url, init) => {
      if (url.endsWith("/assessment/history"))
        return res(200, { surveys: [], attempts: [], cooldowns: [{ profession: "backend", grade: "middle", next_change_at: "2999-10-14T00:00:00Z" }] });
      if (url.endsWith("/assessment/survey") && init?.method === "PUT") return res(200, survey);
      if (url.endsWith("/assessment/attempts") && init?.method === "POST") return res(201, { ...attemptBase, declared_grade: "junior" });
      return surveyGet(url, init);
    });
    expect(await tid("assessment-cooldown")).toHaveTextContent("Следующая попытка Middle");
    expect(screen.getByTestId("assessment-cooldown-date")).toHaveTextContent("14.10.2999");
    expect(screen.getByTestId("assessment-start")).toHaveTextContent("Пройти Junior сейчас");
    fireEvent.click(screen.getByTestId("assessment-start"));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/assessment/attempts") && c.method === "POST")).toBe(true));
    expect(calls.find((c) => c.url.endsWith("/assessment/attempts") && c.method === "POST")!.body).toEqual({ profession: "backend", declared_grade: "junior" });
  });

  it("кулдаун Junior: старта нет, показана дата", async () => {
    mount("/me/assessment?grade=junior", (url, init) => {
      if (url.endsWith("/assessment/history"))
        return res(200, { surveys: [], attempts: [], cooldowns: [], retries: [{ profession: "backend", grade: "junior", next_attempt_at: "2999-10-14T00:00:00Z" }] });
      return surveyGet(url, init);
    });
    await tid("assessment-cooldown");
    expect(screen.getByTestId("assessment-start")).toBeDisabled();
    expect(screen.getByText(/доступно с 14\.10\.2999/)).toBeInTheDocument();
  });

  it("пусто: направление не выбрано, кнопка открывает форму", async () => {
    mount("/me/assessment", (url) => (url.endsWith("/assessment/survey") ? res(200, { ...survey, profession: null, declared_grade: null }) : undefined));
    expect(await tid("assessment-empty")).toHaveTextContent("Направление не выбрано");
    fireEvent.click(screen.getByTestId("assessment-pick"));
    expect(await tid("assessment-survey")).toBeInTheDocument();
  });

  it("загрузка: скелетон; ошибка: «Повторить»", async () => {
    mount("/me/assessment", (url) => (url.endsWith("/assessment/survey") ? res(503, { code: "unavailable" }) : undefined));
    expect(await screen.findByRole("status", { name: "Загружаем…" })).toBeInTheDocument();
    expect(await screen.findByTestId("assessment-error", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });
});

function attemptRoutes(items: unknown[], answers: { body: unknown }[] = []): Handler {
  let i = 0;
  let over = false;
  return (url, init) => {
    if (url.includes("/attempts/a1/next")) {
      const it = items[Math.min(i, items.length - 1)] as { done?: boolean };
      over = !!it.done;
      return res(200, it);
    }
    if (url.endsWith("/attempts/a1/answers")) {
      answers.push({ body: JSON.parse(String(init?.body)) });
      i += 1;
      return res(200, { response_id: "x", accepted: true, done: false });
    }
    if (url.endsWith("/attempts/a1")) return res(200, over ? finished : attemptBase);
  };
}

describe("тест (S2)", () => {
  it("exact: ответ уходит с response_id, rt_ms и телеметрией; после последнего — результат", async () => {
    const answers: { body: unknown }[] = [];
    mount(
      "/me/assessment/attempts/a1",
      attemptRoutes([{ done: false, response_id: "r1", seq: 4, kind: "exact", stem: "Что выведет?\n\nprint(1)", time_limit_s: 120 }, { done: true }], answers),
    );
    const input = await tid("assessment-input-exact");
    expect(screen.getByTestId("assessment-next")).toBeDisabled();
    fireEvent.change(input, { target: { value: "18" } });
    expect(screen.queryByText(/верно|неверно/i)).toBeNull();
    fireEvent.click(screen.getByTestId("assessment-next"));
    await waitFor(() => expect(answers).toHaveLength(1));
    expect(answers[0]!.body).toMatchObject({ response_id: "r1", answer: "18", telemetry: { away_ms: [], pastes: 0 } });
    expect(typeof (answers[0]!.body as { rt_ms: number }).rt_ms).toBe("number");
    expect(await tid("assessment-grade")).toHaveTextContent("Middle");
  });

  it("choice, estimate, find_bug, order передают ответ в своей форме", async () => {
    const answers: { body: unknown }[] = [];
    const items = [
      { done: false, response_id: "c", seq: 1, kind: "choice", stem: "Что проверить?", options: ["A", "B"], time_limit_s: 60 },
      { done: false, response_id: "e", seq: 2, kind: "estimate", stem: "Сколько записей?", time_limit_s: 60 },
      { done: false, response_id: "f", seq: 3, kind: "find_bug", stem: "Найдите.\n\n 1 | def f():\n 2 |     return 1", time_limit_s: 60 },
      { done: false, response_id: "o", seq: 4, kind: "order", stem: "Порядок", options: ["x", "y", "z"], time_limit_s: 60 },
      { done: true },
    ];
    mount("/me/assessment/attempts/a1", attemptRoutes(items, answers));
    fireEvent.click(await tid("assessment-option-0"));
    fireEvent.click(screen.getByTestId("assessment-next"));
    fireEvent.change(await tid("assessment-input-estimate"), { target: { value: "3 000 000" } });
    fireEvent.click(screen.getByTestId("assessment-next"));
    fireEvent.click(await tid("assessment-line-2"));
    expect(screen.getByTestId("assessment-find-hint")).toHaveTextContent("Выбрано строк: 1");
    fireEvent.click(screen.getByTestId("assessment-next"));
    fireEvent.click(await tid("assessment-down-0"));
    fireEvent.click(screen.getByTestId("assessment-next"));
    await waitFor(() => expect(answers).toHaveLength(4));
    expect(answers.map((a) => (a.body as { answer: unknown }).answer)).toEqual([0, 3_000_000, [2], [1, 0, 2]]);
  });

  it("«Не знаю» отправляет null", async () => {
    const answers: { body: unknown }[] = [];
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "c", seq: 1, kind: "choice", stem: "?", options: ["A"], time_limit_s: 60 }, { done: true }], answers));
    fireEvent.click(await tid("assessment-skip"));
    await waitFor(() => expect(answers).toHaveLength(1));
    expect((answers[0]!.body as { answer: unknown }).answer).toBeNull();
  });

  it("chain: шаги по одному, ответ — список, назад нельзя", async () => {
    const answers: { body: unknown }[] = [];
    const chain = {
      done: false,
      response_id: "ch",
      seq: 5,
      kind: "chain",
      stem: "Ночью сервис упал.",
      time_limit_s: 300,
      steps: [
        { kind: "choice", stem: "Что смотрим первым?", options: ["Логи", "Метрики"] },
        { kind: "exact", stem: "Сколько ошибок?" },
      ],
    };
    mount("/me/assessment/attempts/a1", attemptRoutes([chain, { done: true }], answers));
    expect(await tid("assessment-chain-step")).toHaveTextContent("Шаг 1 из 2");
    fireEvent.click(screen.getByTestId("assessment-option-1"));
    fireEvent.click(screen.getByTestId("assessment-next"));
    expect(screen.getByTestId("assessment-chain-step")).toHaveTextContent("Шаг 2 из 2");
    expect(screen.queryByText("Что смотрим первым?")).toBeNull();
    fireEvent.change(screen.getByTestId("assessment-input-exact"), { target: { value: "7" } });
    fireEvent.click(screen.getByTestId("assessment-next"));
    await waitFor(() => expect(answers).toHaveLength(1));
    expect((answers[0]!.body as { answer: unknown }).answer).toEqual([1, "7"]);
  });

  it("таймер: по истечении ответ уходит сам", async () => {
    const answers: { body: unknown }[] = [];
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "t", seq: 1, kind: "exact", stem: "?", time_limit_s: 1 }, { done: true }], answers));
    await screen.findByRole("timer");
    await waitFor(() => expect(answers).toHaveLength(1), { timeout: 3000 });
    expect((answers[0]!.body as { answer: unknown }).answer).toBeNull();
  });

  it("чужая попытка: 404 без кнопки «Повторить»", async () => {
    mount("/me/assessment/attempts/zzz", () => res(404, { code: "not_found" }));
    const box = await tid("assessment-error");
    expect(box).toHaveAttribute("data-code", "not_found");
    expect(within(box).queryByRole("button", { name: "Повторить" })).toBeNull();
  });
});

describe("тест (S2) · макет v2 (E38-4)", () => {
  it("шапка: номер из цели, таймер тикает; «?» открывает правила; «Не знаю» вторичное", async () => {
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "r1", seq: 7, kind: "choice", stem: "Что?", options: ["A", "B"], time_limit_s: 60 }]));
    const timer = await screen.findByRole("timer");
    expect(screen.getByLabelText("Задание 7 из 10")).toBeInTheDocument();
    const before = timer.textContent;
    await waitFor(() => expect(screen.getByRole("timer").textContent).not.toBe(before), { timeout: 3000 });
    expect(screen.queryByText("Правила теста")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Пояснение" }));
    expect(screen.getByText("Правила теста")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-skip").className).toMatch(/border/);
  });

  it("choice: код в условии отдельным блоком, клик по строке выбирает вариант", async () => {
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "c", seq: 1, kind: "choice", stem: "Какой запрос?\n\nusers(id)", options: ["A", "B"], time_limit_s: 60 }]));
    const row = await tid("assessment-option-1");
    expect(screen.getByLabelText("Код задания")).toHaveTextContent("users(id)");
    expect(row).toHaveAttribute("aria-checked", "false");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-checked", "true");
  });

  it("order: клик по строке и по месту переносит вариант", async () => {
    const answers: { body: unknown }[] = [];
    mount(
      "/me/assessment/attempts/a1",
      attemptRoutes([{ done: false, response_id: "o", seq: 1, kind: "order", stem: "Порядок", options: ["x", "y", "z"], time_limit_s: 60 }, { done: true }], answers),
    );
    fireEvent.click(await tid("assessment-row-0"));
    fireEvent.click(screen.getByTestId("assessment-row-2"));
    fireEvent.click(screen.getByTestId("assessment-next"));
    await waitFor(() => expect(answers).toHaveLength(1));
    expect((answers[0]!.body as { answer: unknown }).answer).toEqual([1, 2, 0]);
  });

  it("sjt: строки с номерами и подсказкой про эффективность", async () => {
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "s", seq: 1, kind: "sjt", stem: "Что делать?", options: ["a", "b"], time_limit_s: 60 }]));
    const row = await tid("assessment-row-1");
    expect(row).toHaveTextContent("2");
    expect(screen.getByText(/самого эффективного/)).toBeInTheDocument();
  });

  it("find_bug: строки кода переключаются кликом, ответ — номера строк", async () => {
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "f", seq: 1, kind: "find_bug", stem: "Найдите.\n\n 1 | a\n 2 | b\n 3 | c", time_limit_s: 60 }]));
    fireEvent.click(await tid("assessment-line-3"));
    fireEvent.click(screen.getByTestId("assessment-line-1"));
    expect(screen.getByTestId("assessment-line-3")).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByTestId("assessment-line-3"));
    expect(screen.getByTestId("assessment-find-hint")).toHaveTextContent("Выбрано строк: 1");
  });

  it("пусто: «Активного теста нет» и ссылка на тест; ошибка: «Повторить»; загрузка: скелетон", async () => {
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false }]));
    expect(await screen.findByRole("status", { name: "Загружаем…" })).toBeInTheDocument();
    expect(await tid("assessment-empty")).toHaveTextContent("Активного теста нет");
    expect(screen.getByRole("link", { name: "Пройти тест" })).toHaveAttribute("href", "/me/assessment");
  });

  it("ошибка загрузки задания: «Повторить»", async () => {
    mount("/me/assessment/attempts/a1", (url) => (url.includes("/next") ? res(503, { code: "unavailable" }) : undefined));
    expect(await screen.findByTestId("assessment-error", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  });
});

describe("результат (S3)", () => {
  const routes = (calls: { n: number }): Handler => (url, init) => {
    if (url.endsWith("/attempts/a1/upgrade")) {
      calls.n += 1;
      return res(201, { ...attemptBase, id: "a2", declared_grade: "senior", answered: 0, invited_by: "a1" });
    }
    if (url.includes("/attempts/a2/next")) return res(200, { done: false, response_id: "r1", seq: 1, kind: "exact", stem: "Что выведет?", time_limit_s: 120 });
    if (url.endsWith("/attempts/a2")) return res(200, { ...attemptBase, id: "a2", declared_grade: "senior", answered: 0, invited_by: "a1" });
    if (url.endsWith("/attempts/a1")) return res(200, finished);
    if (url.endsWith("/assessment/history"))
      return res(200, { surveys: [], attempts: [finished], cooldowns: [{ profession: "backend", grade: "middle", next_change_at: "2999-01-04T00:00:00Z" }], retries: [] });
    void init;
  };

  it("грейд, честность, разбор по навыкам, кулдаун и приглашение на тест следующего грейда", async () => {
    const calls = { n: 0 };
    mount("/me/assessment/attempts/a1/result", routes(calls));
    expect(await tid("assessment-grade")).toHaveTextContent("Middle");
    expect(screen.getByTestId("assessment-integrity")).toHaveTextContent("0.92");
    expect(screen.getByTestId("assessment-skill-python")).toHaveTextContent("83%");
    expect(screen.getByTestId("assessment-skill-system_design")).toHaveTextContent("подтянуть");
    expect(await screen.findByText(/Следующая смена грейда — с 04\.01\.2999/)).toBeInTheDocument();
    expect(screen.getByTestId("assessment-invite")).toHaveTextContent("Приглашение на тест Senior");
    expect(screen.getByTestId("assessment-invite-until")).toHaveTextContent("05.11.2999");
    expect(screen.queryByText(/Принять/)).toBeNull(); // ADR-025 п.2: повышения нет, только отдельный тест
    fireEvent.click(screen.getByTestId("assessment-invite-start"));
    await waitFor(() => expect(calls.n).toBe(1));
    expect(await tid("assessment-item")).toBeInTheDocument();
  });

  it("экспресс-результат помечен меткой", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1")) return res(200, { ...finished, mode: "express", invited_grade: null });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-express")).toHaveTextContent("экспресс");
    expect(screen.getByTestId("assessment-confirmed")).toBeInTheDocument();
  });

  it("не прошёл: нейтральный текст без красного акцента", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1"))
        return res(200, { ...finished, status: "failed", invited_grade: null, result: { ...finished.result, grade: null } });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-not-confirmed")).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-invite")).toBeNull();
  });

  it("409 invite_stale показывает понятную ошибку", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1/upgrade")) return res(409, { code: "invite_stale" });
      if (url.endsWith("/attempts/a1")) return res(200, finished);
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [], retries: [] });
    });
    fireEvent.click(await tid("assessment-invite-start"));
    expect(await tid("assessment-invite-error")).toHaveTextContent("неактуально");
  });

  it.each([
    [{ invite_expires_at: "2000-01-01T00:00:00Z" }, "assessment-invite-expired"],
    [{ invite_attempt_id: "a2" }, "assessment-invite-open"],
  ])("приглашение истекло или уже начато: %o", async (patch, testid) => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1")) return res(200, { ...finished, ...patch });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [], retries: [] });
    });
    expect(await tid(testid)).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-invite")).toBeNull();
  });
});

describe("история (S4)", () => {
  it("кулдауны и пересдачи, попытки и опросы", async () => {
    mount("/me/assessment/history", (url) => {
      if (url.endsWith("/assessment/history"))
        return res(200, {
          surveys: [{ id: "s1", profession: "backend", declared_grade: "middle", salary_from: 200000, salary_to: 260000, stack: ["python"], created_at: "2026-10-06T09:00:00Z" }],
          attempts: [finished],
          cooldowns: [{ profession: "backend", grade: "middle", next_change_at: "2999-01-04T00:00:00Z" }],
          retries: [{ profession: "backend", grade: "senior", next_attempt_at: "2000-01-01T00:00:00Z" }],
        });
    });
    const cards = await screen.findAllByTestId("assessment-cooldown-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveAttribute("data-locked", "true");
    expect(within(cards[0]!).getByTestId("assessment-cooldown-locked")).toHaveTextContent("04.01.2999");
    expect(cards[1]).toHaveAttribute("data-locked", "false");
    expect(within(cards[1]!).getByTestId("assessment-cooldown-go")).toHaveAttribute("href", "/me/assessment?profession=backend&grade=senior");
    const row = screen.getByTestId("assessment-attempt-a1");
    expect(row).toHaveTextContent("прошёл");
    expect(row).toHaveTextContent("0.92");
    expect(screen.getByTestId("assessment-attempt-link-a1")).toHaveAttribute("href", "/me/assessment/attempts/a1/result");
    fireEvent.mouseDown(screen.getByTestId("assessment-tab-surveys"));
    expect(await tid("assessment-surveys")).toHaveTextContent("200");
  });

  it("пусто: подсказка и ссылка на опрос", async () => {
    mount("/me/assessment/history", (url) => (url.endsWith("/assessment/history") ? res(200, { surveys: [], attempts: [], cooldowns: [] }) : undefined));
    expect(await screen.findByText("Попыток пока нет")).toBeInTheDocument();
  });
});

describe("«Объясни ответ» (E24-2)", () => {
  const explainOut = {
    response_id: "r2",
    seq: 2,
    skill: "system_design",
    score: 0,
    reason: { code: "misconception", label: "Ложное представление о теме", detail: null },
    misconception: { claim: "Кэш всегда ускоряет.", truth: "Кэш добавляет рассинхрон." },
    text: "Похоже на распространённое заблуждение по этой теме.",
    source: "template",
    model: null,
    self_reason: "guess",
    self_reason_matches: false,
  };

  it("показывает только неверные ответы и объясняет по кнопке, без ключа", async () => {
    const calls = mount("/me/assessment/attempts/a1/result", (url, init) => {
      if (url.includes("/attempts/a1/responses/r2/explain") && init?.method === "POST") return res(200, explainOut);
      if (url.endsWith("/attempts/a1")) return res(200, finished);
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [finished], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-explain")).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-explain-1")).not.toBeInTheDocument(); // верный ответ
    fireEvent.change(screen.getByTestId("assessment-explain-self-2"), { target: { value: "guess" } });
    fireEvent.click(screen.getByTestId("assessment-explain-ask-2"));
    expect(await tid("assessment-explain-out-2")).toHaveTextContent("Кэш добавляет рассинхрон.");
    expect(screen.getByTestId("assessment-explain-reason-2")).toHaveTextContent("Ложное представление о теме");
    const post = calls.find((c) => c.url.includes("/explain"))!;
    expect(post.body).toEqual({ self_reason: "guess" });
  });

  it("ошибка лимита показывается строкой", async () => {
    mount("/me/assessment/attempts/a1/result", (url, init) => {
      if (url.includes("/explain") && init?.method === "POST") return res(429, { code: "rate_limited" });
      if (url.endsWith("/attempts/a1")) return res(200, finished);
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [finished], cooldowns: [], retries: [] });
    });
    fireEvent.click(await tid("assessment-explain-ask-2"));
    expect(await tid("assessment-explain-error-2")).toHaveTextContent("Слишком много запросов");
  });
});
