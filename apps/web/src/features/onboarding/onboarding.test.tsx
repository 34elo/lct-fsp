import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { failureText } from "./text";

interface Call {
  url: string;
  method: string;
  body: unknown;
}
const calls: Call[] = [];
const RID = "11111111-1111-1111-1111-111111111111";
let resume: Record<string, unknown> = { status: "queued" };
let confirmStatus = 200;
let confirmBody: unknown = {};
let uploadStatus = 202;

const parsed = {
  parser_version: "t",
  person: { links: [] },
  experience: [{ company: "Вымысел", title: "Стажёр", start: "2024-01", end: null, skills: ["python"], is_commercial: true }],
  education: [{ institution: "Вуз", field: "Прикладная информатика", year_end: 2026 }],
  skills: [
    { raw: "Python", slug: "python", quote: "Python", method: "llm", confidence: 0.9 },
    { raw: "FastAPI", slug: "fastapi", quote: "FastAPI", method: "llm", confidence: 0.9 },
  ],
  unknown_skills: ["Pydantic"],
  total_experience_months: 6,
  warnings: ["experience_period_invalid", "internal_garbage_code"],
};

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

class FakeES {
  static all: FakeES[] = [];
  handlers: Record<string, ((e: MessageEvent<string>) => void)[]> = {};
  constructor() {
    FakeES.all.push(this);
  }
  addEventListener(t: string, h: (e: MessageEvent<string>) => void) {
    (this.handlers[t] ??= []).push(h);
  }
  close() {}
  emit(t: string, data: unknown) {
    this.handlers[t]?.forEach((h) => h({ data: JSON.stringify(data) } as MessageEvent<string>));
  }
}
const emit = (t: string, data: unknown) => act(() => FakeES.all.forEach((e) => e.emit(t, data)));

beforeEach(() => {
  calls.length = 0;
  FakeES.all = [];
  resume = { status: "queued" };
  confirmStatus = 200;
  confirmBody = {};
  uploadStatus = 202;
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      calls.push({ url, method, body });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.endsWith("/candidates/me/resumes") && method === "POST")
        return uploadStatus === 202 ? res(202, { resume_id: RID, job_id: RID }) : res(uploadStatus, { code: "unsupported_file_type" });
      if (url.endsWith(`/resumes/${RID}/confirm`)) return res(confirmStatus, confirmBody);
      if (url.endsWith(`/resumes/${RID}`)) return res(200, resume);
      if (url.endsWith("/candidates/me/profile")) return res(200, {});
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  render(
    <MemoryRouter initialEntries={["/onboarding"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

async function upload(name = "cv.pdf") {
  const input = (await screen.findByLabelText("Файл резюме")) as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["%PDF-1.4"], name, { type: "application/pdf" })] } });
}

test("лог сборки растёт по job.progress, затем «вот что я понял» и подтверждение с правками", async () => {
  mount();
  await upload();
  const log = await screen.findByRole("log");
  await waitFor(() => expect(FakeES.all.length).toBeGreaterThan(0));
  expect(calls.find((c) => c.method === "POST" && c.url.endsWith("/resumes"))).toBeTruthy();

  await emit("job.progress", { job_id: RID, kind: "resume", stage: "text", pct: 10, message: "Извлекаем текст" });
  await emit("job.progress", { job_id: RID, kind: "resume", stage: "llm", pct: 30, message: "Разбираем опыт и навыки" });
  // чужая задача не попадает в лог
  await emit("job.progress", { job_id: "other", kind: "resume", stage: "verify", pct: 85, message: "Чужой этап" });
  expect(within(log).getByText("Извлекаем текст")).toBeInTheDocument();
  expect(within(log).getByText("Разбираем опыт и навыки")).toBeInTheDocument();
  expect(within(log).queryByText("Чужой этап")).not.toBeInTheDocument();

  resume = { status: "parsed", parsed };
  await emit("resume.parsed", { resume_id: RID });
  expect(await screen.findByRole("heading", { name: "Вот что я понял" })).toBeInTheDocument();
  expect(screen.getByText("Нашёл 2 навыка")).toBeInTheDocument();
  expect(screen.getByText(/Не поняли даты/)).toBeInTheDocument();
  expect(screen.queryByText(/internal_garbage_code/)).not.toBeInTheDocument();
  expect(screen.getByText("Pydantic")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Убрать навык FastAPI" }));
  fireEvent.change(screen.getByLabelText("Добавить навык"), { target: { value: " Redis " } });
  fireEvent.click(screen.getByRole("button", { name: "Добавить" }));
  fireEvent.click(screen.getByRole("button", { name: /Поправить: Стажёр/ }));
  fireEvent.change(screen.getByLabelText("Должность"), { target: { value: "Разработчик" } });
  fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
  expect(screen.getByText("Разработчик")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Всё верно" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/confirm"))).toBe(true));
  const edits = (calls.find((c) => c.url.endsWith("/confirm"))!.body as { edits: Record<string, unknown> }).edits;
  expect(edits.remove_skills).toEqual(["fastapi"]);
  expect(edits.add_skills).toEqual(["redis"]);
  expect(edits.experience).toMatchObject([{ title: "Разработчик", company: "Вымысел" }]);
  expect(edits.education).toBeUndefined(); // не трогали — не отправляем
  expect(await screen.findByText(/навыков: 3/)).toBeInTheDocument(); // Python + Redis + Pydantic (новый); FastAPI убран
  fireEvent.click(await screen.findByRole("button", { name: "Пропустить" }));
  expect(await screen.findByRole("link", { name: "Смотреть мой профиль" })).toHaveAttribute("href", "/me");
});

test("без правок отправляются только пустые списки", async () => {
  resume = { status: "parsed", parsed };
  mount();
  await upload();
  fireEvent.click(await screen.findByRole("button", { name: "Всё верно" }));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/confirm"))).toBe(true));
  expect((calls.find((c) => c.url.endsWith("/confirm"))!.body as { edits: unknown }).edits).toEqual({
    remove_skills: [],
    add_skills: [],
  });
});

test("неизвестный навык при подтверждении — понятная ошибка, остаёмся на экране", async () => {
  resume = { status: "parsed", parsed };
  confirmStatus = 422;
  confirmBody = { code: "unknown_skill", errors: [{ field: "add_skills", message: "zzz" }] };
  mount();
  await upload();
  fireEvent.click(await screen.findByRole("button", { name: "Всё верно" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("zzz");
  expect(screen.getByRole("heading", { name: "Вот что я понял" })).toBeInTheDocument();
});

test("сбой разбора показывает причину и даёт загрузить заново", async () => {
  resume = { status: "failed", error: "scanned_pdf" };
  mount();
  await upload();
  expect(await screen.findByRole("alert")).toHaveTextContent("скан");
  expect(screen.getByRole("button", { name: "Выбрать файл" })).toBeEnabled();
});

test("не тот тип файла отсекается до отправки; ошибка сервера 415 — сообщением", async () => {
  mount();
  await upload("cv.txt");
  expect(await screen.findByRole("alert")).toHaveTextContent("PDF и DOCX");
  expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/resumes"))).toBe(false);
  uploadStatus = 415;
  await upload("cv.pdf");
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/resumes"))).toBe(true));
  expect(await screen.findByRole("alert")).toHaveTextContent("PDF и DOCX");
});

test("шаги можно пропустить до конца", async () => {
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Пропустить, заполню вручную" }));
  fireEvent.click(await screen.findByRole("button", { name: "Пропустить" }));
  expect(await screen.findByRole("link", { name: "Смотреть мой профиль" })).toBeInTheDocument();
  expect(screen.getAllByText(/пропущено/)).toHaveLength(2);
  expect(screen.getByTestId("onboarding-to-profile")).toBeInTheDocument();
});

test("один шаг на экран: схемная линия отмечает текущий шаг, остальные шаги не показаны", async () => {
  mount();
  expect(await screen.findByTestId("onboarding-step-resume")).toBeInTheDocument();
  expect(screen.queryByTestId("onboarding-step-fsp")).not.toBeInTheDocument();
  const current = screen.getByRole("list", { name: "Этапы" }).querySelector('[aria-current="step"]');
  expect(current).toHaveTextContent("Резюме");
  fireEvent.click(screen.getByTestId("onboarding-skip"));
  expect(await screen.findByTestId("onboarding-step-fsp")).toBeInTheDocument();
  expect(screen.queryByTestId("onboarding-step-resume")).not.toBeInTheDocument();
});

describe("failureText", () => {
  it("llm_unavailable: понятное сообщение без фикстуры", () => {
    expect(failureText("llm_unavailable")).toBe("Разбор резюме сейчас недоступен, заполните данные вручную.");
  });
});
