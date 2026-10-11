import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { pickOption } from "@/test-pick";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const professions = {
  professions: [
    { slug: "backend", title: "Backend-разработчик", skill_weights: {}, skill_types: {} },
    { slug: "frontend", title: "Frontend-разработчик", skill_weights: {}, skill_types: {} },
    { slug: "mobile", title: "Мобильный разработчик", skill_weights: {}, skill_types: {}, beta: true },
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
    se: 0.2,
    theta_by_type: { hard: 0.2, fundamental: 0.6, soft: -0.4 },
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

describe("поток до теста (S1)", () => {
  it("предзаполняет шаги 1–2, сохраняет и начинает тест", async () => {
    const calls = mount("/me/assessment", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, survey);
      if (url.endsWith("/assessment/survey")) return res(200, { ...survey, id: "s1", prefilled: false });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [] });
      if (url.endsWith("/assessment/attempts") && init?.method === "POST") return res(201, attemptBase);
      if (url.includes("/attempts/a1/next")) return res(200, { done: false, response_id: "r1", seq: 4, kind: "exact", stem: "Что выведет?", time_limit_s: 120 });
      if (url.endsWith("/attempts/a1")) return res(200, attemptBase);
    });
    expect(await tid("assessment-prefilled")).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-industry")).toBeNull(); // отрасль не спрашиваем
    expect(screen.getByTestId("flow-step-1")).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("heading", { name: "Направление и навыки" })).toBeInTheDocument();
    expect(screen.getByTestId("assessment-profession-backend")).toBeChecked();
    fireEvent.change(screen.getByTestId("assessment-stack-input"), { target: { value: "Redis" } });
    fireEvent.keyDown(screen.getByTestId("assessment-stack-input"), { key: "Enter" });
    expect(within(screen.getByTestId("assessment-stack")).getByText(/redis/)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("assessment-next"));
    expect(await tid("assessment-step-2")).toBeInTheDocument();
    expect(screen.getByTestId("flow-step-2")).toHaveAttribute("aria-current", "step");
    expect(screen.getByTestId("assessment-grade-middle")).toBeChecked();
    fireEvent.click(screen.getByTestId("assessment-start"));
    expect(await tid("assessment-item")).toBeInTheDocument();
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.body).toMatchObject({ industry: "Электронная коммерция", profession: "backend", declared_grade: "middle", stack: ["python", "fastapi", "redis"], salary_from: 200000 });
    expect(calls.find((c) => c.url.endsWith("/assessment/attempts") && c.method === "POST")!.body).toEqual({ profession: "backend", declared_grade: "middle" });
  });

  it("экспресс-режим: ?mode=express включает переключатель, попытка создаётся с mode", async () => {
    const calls = mount("/me/assessment?mode=express", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, survey);
      if (url.endsWith("/assessment/survey")) return res(200, { ...survey, id: "s1", prefilled: false });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [] });
      if (url.endsWith("/assessment/attempts") && init?.method === "POST") return res(201, { ...attemptBase, mode: "express", target: 6 });
      if (url.includes("/attempts/a1/next")) return res(200, { done: false, response_id: "r1", seq: 1, kind: "exact", stem: "Что выведет?", time_limit_s: 120 });
      if (url.endsWith("/attempts/a1")) return res(200, { ...attemptBase, mode: "express", target: 6 });
    });
    fireEvent.click(await tid("assessment-next"));
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
    fireEvent.click(await tid("assessment-next"));
    fireEvent.click(await tid("assessment-start"));
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
    fireEvent.click(await tid("assessment-next"));
    fireEvent.click(await tid("assessment-start"));
    const err = await tid("assessment-start-error");
    expect(err).toHaveTextContent("04.11.2026");
    expect(err).toHaveAttribute("data-code", "cooldown");
    code = "email";
    fireEvent.click(screen.getByTestId("assessment-start"));
    await waitFor(() => expect(screen.getByTestId("assessment-start-error")).toHaveAttribute("data-code", "email_not_verified"));
    expect(within(screen.getByTestId("assessment-start-error")).getByRole("link")).toHaveAttribute("href", "/verify-email");
  });
});

describe("поток до теста (S1) · состояния", () => {
  const surveyGet = (url: string, init?: RequestInit) => (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET" ? res(200, survey) : undefined);

  it("кулдаун: плашка с датой, грейд в контуре, старт предлагает грейд ниже", async () => {
    const calls = mount("/me/assessment", (url, init) => {
      if (url.endsWith("/assessment/history"))
        return res(200, { surveys: [], attempts: [], cooldowns: [{ profession: "backend", grade: "middle", next_change_at: "2999-10-14T00:00:00Z" }] });
      if (url.endsWith("/assessment/survey") && init?.method === "PUT") return res(200, survey);
      if (url.endsWith("/assessment/attempts") && init?.method === "POST") return res(201, { ...attemptBase, declared_grade: "junior" });
      return surveyGet(url, init);
    });
    fireEvent.click(await tid("assessment-next"));
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

  it("пусто: без направления дальше не пройти; все профессии выбираются, «бета» помечена", async () => {
    mount("/me/assessment", (url) => (url.endsWith("/assessment/survey") ? res(200, { ...survey, profession: null, declared_grade: null }) : undefined));
    fireEvent.click(await tid("assessment-next"));
    expect(await tid("assessment-need-profession")).toBeInTheDocument();
    expect(screen.queryByTestId("assessment-step-2")).toBeNull();
    expect(screen.getByTestId("assessment-beta-mobile")).toHaveTextContent("бета");
    expect(screen.queryByTestId("assessment-beta-backend")).toBeNull();
    for (const p of professions.professions) {
      fireEvent.click(screen.getByTestId(`assessment-profession-${p.slug}`));
      expect(screen.getByTestId(`assessment-profession-${p.slug}`)).toBeChecked();
    }
    fireEvent.click(screen.getByTestId("assessment-next"));
    expect(await tid("assessment-step-2")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("assessment-back"));
    expect(await tid("assessment-step-1")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-profession-mobile")).toBeChecked();
  });

  it("из профиля (?step=1): направление и навыки сохраняются без теста", async () => {
    const calls = mount("/me/assessment?step=1", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, { ...survey, id: "s1", prefilled: false });
      if (url.endsWith("/assessment/survey")) return res(200, { ...survey, id: "s2", prefilled: false });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [] });
    });
    fireEvent.click(await tid("assessment-profession-frontend"));
    fireEvent.click(screen.getByTestId("assessment-save-step"));
    expect(await tid("assessment-saved")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-later")).toHaveAttribute("href", "/me/profile");
    expect(calls.find((c) => c.method === "PUT")!.body).toMatchObject({ profession: "frontend", declared_grade: "middle" });
    expect(calls.some((c) => c.url.endsWith("/assessment/attempts"))).toBe(false);
  });

  it("сохранённое направление: сразу шаг 2", async () => {
    mount("/me/assessment", (url) => (url.endsWith("/assessment/survey") ? res(200, { ...survey, id: "s1", prefilled: false }) : undefined));
    expect(await tid("assessment-step-2")).toBeInTheDocument();
    expect(screen.getByTestId("flow-step-1")).toHaveAttribute("data-state", "done");
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

  it("«Не знаю»: после пустого ответа показано следующее задание, а не то же", async () => {
    const answers: { body: unknown }[] = [];
    mount(
      "/me/assessment/attempts/a1",
      attemptRoutes(
        [
          { done: false, response_id: "r1", seq: 1, kind: "choice", stem: "Первое?", options: ["A"], time_limit_s: 60 },
          { done: false, response_id: "r2", seq: 2, kind: "choice", stem: "Второе?", options: ["B"], time_limit_s: 60 },
        ],
        answers,
      ),
    );
    expect(await screen.findByRole("heading", { name: "Первое?" })).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("assessment-skip"));
    expect(await screen.findByRole("heading", { name: "Второе?" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Первое?" })).toBeNull();
  });

  it("choice: варианты — радиокнопки с подписями, группа подписана условием", async () => {
    mount("/me/assessment/attempts/a1", attemptRoutes([{ done: false, response_id: "c", seq: 1, kind: "choice", stem: "Что?", options: ["Альфа", "Бета"], time_limit_s: 60 }]));
    expect(await screen.findByRole("radiogroup", { name: "Что?" })).toBeInTheDocument();
    const radio = screen.getByRole("radio", { name: "Бета" });
    fireEvent.click(radio);
    expect(radio).toBeChecked();
    expect(screen.getByRole("radio", { name: "Альфа" })).not.toBeChecked();
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

describe("тест (S2) · макет v2", () => {
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
    fireEvent.click(screen.getByTestId("assessment-topics-toggle"));
    expect(screen.getByTestId("assessment-skill-python")).toHaveTextContent("83%");
    expect(screen.getByTestId("assessment-skill-system_design")).toHaveTextContent("подтянуть");
    expect(await screen.findByText(/Следующая смена грейда — с 04\.01\.2999/)).toBeInTheDocument();
    expect(screen.getByTestId("assessment-invite")).toHaveTextContent("Приглашение на тест Senior");
    expect(screen.getByTestId("assessment-invite-until")).toHaveTextContent("05.11.2999");
    expect(screen.queryByText(/Принять/)).toBeNull(); // повышения нет, только отдельный тест
    fireEvent.click(screen.getByTestId("assessment-invite-start"));
    await waitFor(() => expect(calls.n).toBe(1));
    expect(await tid("assessment-item")).toBeInTheDocument();
  });

  it("макет v2: шкала 0–100 с порогом следующего грейда, разбивка по типам, «?»", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1")) return res(200, { ...finished, invited_grade: null });
      if (url.endsWith("/candidates/me/interests")) return res(200, { companies: 3, salary_from_min: 140000, salary_to_max: 220000, items: [] });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [finished], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-grade")).toHaveTextContent("Backend-разработчик · Middle — подтверждён");
    // θ 0.4 → 55 + 25·0.4 = 65; подтверждён Middle → порог Senior (θ 1 → 80)
    expect(screen.getByTestId("assessment-scale-aside")).toHaveTextContent("твой результат 65 · порог Senior 80");
    expect(screen.getByRole("img", { name: /Результат 65/ })).toBeInTheDocument();
    const types = screen.getByTestId("assessment-types");
    expect(within(types).getAllByText(/Фундамент|Хард|Софт/).map((e) => e.textContent)).toEqual(["Фундамент", "Хард", "Софт"]);
    expect(within(types).getByText("70")).toBeInTheDocument(); // фундамент θ 0.6
    expect(await tid("assessment-opened-count")).toHaveTextContent("3");
    expect(screen.getByTestId("assessment-to-offers")).toHaveAttribute("href", "/me/offers");
    expect(screen.getByTestId("assessment-to-growth")).toHaveAttribute("href", "/me/navigator");
    expect(screen.queryByTestId("assessment-rules")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Как устроен тест" }));
    expect(screen.getByTestId("assessment-rules")).toHaveTextContent("90 дней");
    expect(screen.queryByTestId("assessment-skills")).toBeNull();
    fireEvent.click(screen.getByTestId("assessment-topics-toggle"));
    expect(screen.getByTestId("assessment-skills")).toBeInTheDocument();
  });

  it("не подтверждён: главная — тест грейдом ниже, заявленный стек пунктиром", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1"))
        return res(200, { ...finished, status: "failed", invited_grade: null, result: { ...finished.result, grade: null, theta: -0.4 } });
      if (url.endsWith("/assessment/history"))
        return res(200, { surveys: [{ ...survey, id: "s1", created_at: "2026-10-06T08:00:00Z" }], attempts: [], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-grade")).toHaveTextContent("Middle не подтверждён");
    expect(screen.getByTestId("assessment-scale-aside")).toHaveTextContent("твой результат 45 · порог Middle 55");
    expect(screen.getByTestId("assessment-lower")).toHaveAttribute("href", "/me/assessment?profession=backend&grade=junior");
    expect(screen.getByTestId("assessment-lower")).toHaveTextContent("Пройти Junior сейчас");
    expect(screen.getByTestId("assessment-to-profile")).toHaveAttribute("href", "/me");
    const claimed = await tid("assessment-claimed");
    expect(within(claimed).getByText("fastapi")).toBeInTheDocument();
    expect(claimed).toHaveTextContent("200 000");
    expect(screen.getByTestId("assessment-explain")).toHaveTextContent("Задание 2");
  });

  it("загрузка: скелетон по композиции; ошибка: «Повторить»; чужая попытка: 404 без повтора", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => (url.endsWith("/attempts/a1") ? res(503, { code: "unavailable" }) : undefined));
    expect(await tid("assessment-result-loading")).toBeInTheDocument();
    expect(await screen.findByTestId("assessment-error", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
    cleanup();
    mount("/me/assessment/attempts/a1/result", () => undefined);
    expect(await tid("assessment-error")).toHaveTextContent("Попытка не найдена");
    expect(screen.queryByRole("button", { name: "Повторить" })).toBeNull();
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

describe("«Объясни ответ»", () => {
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
    fireEvent.click(screen.getByTestId("assessment-explain-ask-2"));
    expect(await tid("assessment-explain-out-2")).toHaveTextContent("Кэш добавляет рассинхрон.");
    expect(screen.getByTestId("assessment-explain-reason-2")).toHaveTextContent("Ложное представление о теме");
    expect(calls.find((c) => c.url.includes("/explain"))!.body).toBeUndefined();
    // своя версия причины — после первого разбора, затем сверка
    pickOption(screen.getByTestId("assessment-explain-self-2"), "Угадывал");
    fireEvent.click(screen.getByTestId("assessment-explain-ask-2"));
    await waitFor(() => expect(calls.filter((c) => c.url.includes("/explain"))).toHaveLength(2));
    expect(calls.filter((c) => c.url.includes("/explain"))[1]!.body).toEqual({ self_reason: "guess" });
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

describe("баннер пути кандидата", () => {
  const history = (surveys: unknown[], attempts: unknown[]) => (url: string) =>
    url.endsWith("/assessment/history") ? res(200, { surveys, attempts, cooldowns: [], retries: [] }) : undefined;

  it("без направления на экране кандидата — одна кнопка в поток до теста", async () => {
    mount("/me/offers", history([], []));
    const banner = await screen.findByTestId("path-banner");
    expect(banner).toHaveAttribute("data-step", "survey");
    const links = within(banner).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/me/assessment");
    expect(links[0]).toHaveTextContent("Выбрать направление");
  });

  it("направление есть, теста нет — «Пройти тест»; идёт попытка — «Продолжить тест»", async () => {
    mount("/me/offers", history([{ id: "s1" }], []));
    expect(await screen.findByTestId("path-banner-action")).toHaveTextContent("Пройти тест");
    cleanup();
    mount("/me/offers", history([{ id: "s1" }], [attemptBase]));
    expect(await screen.findByTestId("path-banner-action")).toHaveAttribute("href", "/me/assessment/attempts/a1");
  });

  it("после теста баннера нет; на экране потока до теста — тоже", async () => {
    const calls = mount("/me/offers", history([{ id: "s1" }], [finished]));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/assessment/history"))).toBe(true));
    await waitFor(() => expect(screen.queryByTestId("path-banner")).not.toBeInTheDocument());
    cleanup();
    mount("/me/assessment", (url) => (url.endsWith("/assessment/survey") ? res(200, survey) : history([], [])(url)));
    expect(await screen.findByTestId("assessment-survey")).toBeInTheDocument();
    expect(screen.queryByTestId("path-banner")).not.toBeInTheDocument();
  });
});

describe("путь: тест сейчас или позже, результат → Главная", () => {
  it("«Сохранить, тест позже» предлагает пройти тест позже и ведёт на Главную", async () => {
    mount("/me/assessment", (url, init) => {
      if (url.endsWith("/assessment/survey") && (init?.method ?? "GET") === "GET") return res(200, survey);
      if (url.endsWith("/assessment/survey")) return res(200, { ...survey, id: "s1", prefilled: false });
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [], cooldowns: [] });
    });
    fireEvent.click(await tid("assessment-next"));
    fireEvent.click(await tid("assessment-save"));
    expect(await tid("assessment-saved")).toHaveTextContent("позже");
    expect(screen.getByTestId("assessment-later")).toHaveAttribute("href", "/me");
  });

  it("результат: главная кнопка — «На главную»", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1")) return res(200, finished);
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [finished], cooldowns: [], retries: [] });
    });
    const home = await tid("assessment-to-profile");
    expect(home).toHaveAttribute("href", "/me");
    expect(home).toHaveTextContent("На главную");
  });
});

describe("разбор теста", () => {
  const part = { kind: "exact", stem: "Сколько будет 2+2?", reason: { code: "calc_error", label: "Ошибка в вычислении", detail: null } };
  const review = {
    attempt_id: "a1",
    profession: "backend",
    items: [
      { ...part, response_id: "r1", seq: 1, skill: "python", skill_type: "hard", score: 0.5, time_limit_s: 60, why: "Найдена только часть.", yours: "4" },
      { ...part, response_id: "r2", seq: 2, skill: "system_design", skill_type: "thinking", score: 0, time_limit_s: 60, why: "Пройдите по шагам.", yours: "5" },
    ],
  };
  const handler = (url: string) => {
    if (url.endsWith("/attempts/a1/review")) return res(200, review);
  };

  it("группы по типам, ответы, «что подтянуть»; объяснения скрываются и запоминаются", async () => {
    localStorage.clear();
    mount("/me/assessment/attempts/a1/review", handler);
    expect(await tid("assessment-review-group-hard")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-review-group-thinking")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-review-item-2-yours")).toHaveTextContent("5");
    // верных ответов в разборе нет
    expect(screen.queryByTestId("assessment-review-item-2-correct")).toBeNull();
    expect(screen.queryByText(/Верный ответ/)).toBeNull();
    expect(screen.getByTestId("assessment-review-item-2")).toHaveAttribute("data-verdict", "bad");
    expect(screen.getByTestId("assessment-review-weak-system_design")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-review-weak-python")).toBeInTheDocument();
    expect(screen.getByTestId("assessment-review-to-growth")).toHaveAttribute("href", "/me/navigator");

    // сворачивание у одного задания
    fireEvent.click(screen.getByTestId("assessment-review-item-2-toggle"));
    expect(screen.queryByText("Пройдите по шагам.")).toBeNull();
    expect(screen.getByTestId("assessment-review-item-1-why")).toBeInTheDocument();

    // общий переключатель скрывает объяснения и помнится
    fireEvent.click(screen.getByTestId("assessment-review-hide-switch"));
    expect(screen.queryByTestId("assessment-review-item-1-why")).toBeNull();
    expect(localStorage.getItem("fsp.assessment.review.hideExplain")).toBe("1");
    cleanup();
    mount("/me/assessment/attempts/a1/review", handler);
    await tid("assessment-review-group-hard");
    expect(screen.getByTestId("assessment-review-hide-switch")).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByTestId("assessment-review-item-1-why")).toBeNull();
    localStorage.clear();
  });

  it("идущая попытка (409) — «тест ещё идёт», чужая (404) — не найдено", async () => {
    mount("/me/assessment/attempts/a1/review", (url) => (url.endsWith("/review") ? res(409, { code: "attempt_active", title: "x" }) : undefined));
    expect(await tid("assessment-review-active")).toBeInTheDocument();
    cleanup();
    mount("/me/assessment/attempts/zz/review", () => undefined);
    expect(await tid("assessment-error")).toBeInTheDocument();
  });

  it("из результата и истории есть ссылка на разбор", async () => {
    mount("/me/assessment/attempts/a1/result", (url) => {
      if (url.endsWith("/attempts/a1")) return res(200, finished);
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [finished], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-to-review")).toHaveAttribute("href", "/me/assessment/attempts/a1/review");
    cleanup();
    mount("/me/assessment/history", (url) => {
      if (url.endsWith("/assessment/history")) return res(200, { surveys: [], attempts: [finished], cooldowns: [], retries: [] });
    });
    expect(await tid("assessment-attempt-review-a1")).toHaveAttribute("href", "/me/assessment/attempts/a1/review");
  });
});
