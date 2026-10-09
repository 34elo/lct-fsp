import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const base = {
  pseudonym: "Backend #4821",
  profile_version: 3,
  search_status: "active",
  active_until: "2026-10-20T00:00:00Z",
  preferences: { work_format: [], relocation: false },
  visibility: { public_profile: false, teams: true },
  claimed_soft: ["коммуникабельный"],
  experience: [],
};
const ev = { id: "e1", source: "fsp", strength: 0.9, observed_at: "2026-01-10", title: "Кубок ФСП, финал, 2 место из 120", verified: true };
const full = {
  ...base,
  category: { primary_role: "backend", roles: [{ role: "backend", weight: 0.9 }], primary_stack: ["Python"] },
  grade: {
    grade: "junior_plus",
    score: 4.5,
    confidence: 0.4,
    preliminary: true,
    breakdown: [
      { signal: "experience", label: "Стаж", points: 3, evidence_ids: [] },
      { signal: "fsp_achievement", label: "Достижение на соревнованиях ФСП", points: 2, evidence_ids: ["e1"] },
    ],
    next_grade: { grade: "middle", points_needed: 1.5, hints: ["Пройдите тест"] },
  },
  skills: [
    { skill: { slug: "python", name: "Python", group: "language" }, confidence: 0.8, level: 3, sources: ["fsp"], claimed_only: false, status: "active", derived_from: null, top_evidence: [ev] },
    { skill: { slug: "redis", name: "Redis", group: "db" }, confidence: 0.2, level: 0, sources: ["resume"], claimed_only: true, status: "active", derived_from: null, top_evidence: [] },
  ],
  team_signals: [{ signal: "leadership", value: 0.7, label: "strong", facts: [{ fact_id: "f1", title: "Капитан команды, 2026" }] }],
};
const parsedResume = {
  parser_version: "fake",
  person: { full_name: "Анна Резюмеева", email: "anna@cv.test", phone: null, telegram: null, links: ["https://github.com/anna-cv", "не ссылка"] },
  experience: [{ company: "Кедр Софт", title: "Backend-разработчик", start: "2022-03", end: null, description: "API", skills: ["python"], is_commercial: true }],
  education: [{ institution: "МГТУ", degree: "бакалавр", field: "ИВТ", year_end: 2021 }],
  skills: [
    { slug: "python", name: "Python" },
    { slug: "redis", name: "Redis" },
  ],
  unknown_skills: [],
};
let profile: unknown = full;
let standing: unknown = null;
let evidenceStatus = 200;
let resume: unknown = null;
type Call = { url: string; method: string; body: unknown };
let calls: Call[] = [];

class NoES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("EventSource", NoES);
  profile = full;
  evidenceStatus = 200;
  standing = null;
  resume = null;
  calls = [];
  setAccessToken(null);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
      if (method !== "GET" && !url.endsWith("/auth/refresh")) calls.push({ url, method, body });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.endsWith("/candidates/me/profile") && method === "PATCH") return res(200, { ...(profile as object), ...(body as object) });
      if (url.endsWith("/candidates/me/profile")) return res(200, profile);
      if (url.endsWith("/candidates/me/resumes") && method === "POST") {
        resume = { status: "parsed", parsed: parsedResume };
        return res(202, { resume_id: "r1", job_id: "j1" });
      }
      if (url.endsWith("/candidates/me/resumes/r1/confirm")) return res(200, { status: "confirmed", parsed: parsedResume });
      if (url.endsWith("/candidates/me/resumes/r1")) return resume ? res(200, resume) : res(404);
      if (url.endsWith("/candidates/me/fsp")) return res(200, { link: { linked: false, verified: false }, achievements: [], ranks: [], teams: [] });
      if (url.endsWith("/candidates/me/standing")) return standing ? res(200, standing) : res(404);
      if (url.includes("/candidates/me/graph")) return res(200, { nodes: [], edges: [] });
      if (url.endsWith("/candidates/me/skills/python/evidence")) return evidenceStatus === 200 ? res(200, [ev]) : res(404, { code: "skill_not_found" });
      if (url.includes("/candidates/me/skills/")) return res(404, { code: "skill_not_found" });
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

test("обзор: грейд и статус, плитки, заявлено и подтверждено, командные сигналы; без онбординга и заданий", async () => {
  mount("/me/profile");
  expect(await screen.findByRole("heading", { name: "Профиль", level: 1 })).toBeInTheDocument();
  const card = await screen.findByTestId("profile-status-card");
  expect(within(card).getByTestId("profile-grade")).toHaveTextContent("Junior+ · Backend");
  expect(within(card).getByTestId("profile-grade-status")).toHaveTextContent("не подтверждён");
  expect(within(card).getByText(/Предварительно.*уверенность 40%/)).toBeInTheDocument();
  expect(within(card).getByTestId("profile-published")).toHaveTextContent("профиль опубликован");
  expect(screen.getByTestId("profile-tile-confirmed")).toHaveTextContent("1");
  expect(screen.getByTestId("profile-tile-claimed")).toHaveTextContent("1");
  expect(screen.queryByRole("region", { name: "Почему такой грейд" })).not.toBeInTheDocument();
  const team = screen.getByRole("region", { name: "Командные сигналы" });
  expect(within(team).getByText("Лидерство")).toBeInTheDocument();
  expect(within(team).getByText("Капитан команды, 2026")).toBeInTheDocument();
  expect(within(team).getByText(/коммуникабельный/)).toBeInTheDocument();
  expect(screen.getByTestId("profile-tab-overview")).toHaveAttribute("data-state", "active");
  expect(document.querySelector('a[href="/onboarding"]')).toBeNull();
  expect(document.querySelector('a[href="/me/tasks"]')).toBeNull();
  expect(within(screen.getByTestId("profile-strength")).getByRole("link", { name: "добавить: Тест" })).toHaveAttribute("href", "/me/assessment");
});

test("обзор: подтверждённый тестом грейд", async () => {
  standing = { profession: "backend", grade: "junior", mode: "express", confirmed_at: "2026-10-07T10:00:00Z" };
  mount("/me/profile");
  const card = await screen.findByTestId("profile-status-card");
  await waitFor(() => expect(within(card).getByTestId("profile-grade-status")).toHaveTextContent("подтверждён 07.10 · экспресс"));
  expect(within(card).getByTestId("profile-grade")).toHaveTextContent("Junior · Backend");
});

test("вкладки «Обзор · Навыки · Данные · Граф» листаются по горизонтали; старая «ФСП» ведёт в «Данные»", async () => {
  mount("/me/profile?tab=fsp");
  const tabs = await screen.findByTestId("profile-tabs");
  expect(within(tabs).getAllByRole("tab").map((t) => t.textContent)).toEqual(["Обзор", "Навыки", "Данные", "Граф"]);
  expect(tabs.className).toMatch(/overflow-x-auto/);
  expect(screen.getByTestId("profile-tab-data")).toHaveAttribute("data-state", "active");
  expect(await screen.findByTestId("profile-data")).toBeInTheDocument();
  fireEvent.mouseDown(screen.getByTestId("profile-tab-skills"), { button: 0 });
  expect(await screen.findByTestId("profile-skills")).toBeInTheDocument();
});

const many = Array.from({ length: 20 }, (_, i) => ({
  skill: { slug: `s${i}`, name: `Навык ${i}`, group: "language", type: i % 2 ? "hard" : "fundamental" },
  confidence: 0.9 - i * 0.01,
  level: i < 10 ? 3 : 1,
  sources: ["test"],
  claimed_only: i >= 16,
  status: "active",
  derived_from: null,
  top_evidence: [],
}));

test("навыки: по умолчанию 15, поиск, «подтверждено/заявлено», показать все", async () => {
  profile = { ...full, skills: many };
  mount("/me/profile?tab=skills");
  const list = await screen.findByTestId("profile-skills-list");
  expect(within(list).getAllByRole("listitem")).toHaveLength(15);
  expect(screen.getByTestId("profile-skills-count")).toHaveTextContent("Показано 15 из 20");
  expect(screen.queryByText("Заявлено и подтверждено")).not.toBeInTheDocument(); // блоки грейда — в «Обзоре»
  fireEvent.click(screen.getByTestId("profile-skills-all"));
  expect(within(screen.getByTestId("profile-skills-list")).getAllByRole("listitem")).toHaveLength(20);
  fireEvent.click(screen.getByTestId("profile-skills-state-claimed"));
  expect(within(screen.getByTestId("profile-skills-list")).getAllByRole("listitem")).toHaveLength(4);
  fireEvent.click(screen.getByTestId("profile-skills-state-all"));
  fireEvent.change(screen.getByTestId("profile-skills-search"), { target: { value: "навык 1" } });
  expect(within(screen.getByTestId("profile-skills-list")).getAllByRole("listitem")).toHaveLength(11); // 1, 10–19
  fireEvent.change(screen.getByTestId("profile-skills-search"), { target: { value: "нет такого" } });
  expect(screen.getByText("Ничего не нашлось")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("profile-skills-reset"));
  expect(screen.getByTestId("profile-skills-count")).toHaveTextContent("Показано 20 из 20");
});

test("навыки: скрытие уходит в PATCH hidden_skills, скрытые видны только по флажку", async () => {
  profile = { ...full, hidden_skills: ["redis"] };
  mount("/me/profile?tab=skills");
  const list = await screen.findByTestId("profile-skills-list");
  expect(within(list).queryByTestId("profile-skill-redis")).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId("profile-skills-show-hidden"));
  expect(await screen.findByTestId("profile-skill-redis")).toHaveTextContent("скрыт от компаний");
  fireEvent.click(screen.getByRole("button", { name: "Скрыть Python от компаний" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ hidden_skills: ["python", "redis"] }));
});

test("данные: ФИО, контакты, опыт, образование, ссылки в одном формате; ФСП отдельной карточкой", async () => {
  profile = {
    ...full,
    full_name: "Анна Иванова",
    contacts: { email: "anna@x.test", phone: null, telegram: "@anna_dev" },
    visibility: { full_name: false },
    preferences: { city: "Санкт-Петербург", salary_min: 70000, formats: ["remote", "hybrid"], employment_types: [], relocation: false },
    experience: [{ title: "Backend-разработчик", company: "Кедр Софт", start: "2024-08", end: null, skills: [] }],
    education: [{ institution: "МГТУ", degree: "бакалавр", field: "ИВТ", year_end: 2021 }],
    links: ["https://github.com/anna"],
    fsp: {
      verified: true,
      achievements: [{ fact_id: "f1", title: "Финал по продуктовому программированию", level: "national", place: 2, of: 40, year: 2026, team_role: "captain" }],
      ranks: [{ discipline: "product", rank: "rank_2" }],
    },
  };
  mount("/me/profile?tab=data");
  const personal = await screen.findByRole("region", { name: "Личные данные" });
  expect(within(personal).getByText("Анна Иванова")).toBeInTheDocument();
  expect(within(personal).getByText(/Компания увидит после приглашения/)).toBeInTheDocument();
  expect(within(personal).getByText("@anna_dev")).toBeInTheDocument();
  const exp = screen.getByRole("region", { name: "Опыт" });
  expect(within(exp).getByText(/Кедр Софт/)).toBeInTheDocument();
  expect(within(exp).getByText("2024 — по сей день")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Образование" })).getByText("МГТУ")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Ссылки" })).getByRole("link", { name: "https://github.com/anna" })).toHaveAttribute("rel", expect.stringContaining("noopener"));
  expect(within(screen.getByRole("region", { name: "Пожелания к работе" })).getByText("удалёнка или гибрид")).toBeInTheDocument();
  const fsp = screen.getByRole("region", { name: "Достижения ФСП" });
  expect(within(fsp).getByText(/Финал по продуктовому программированию/)).toBeInTheDocument();
  expect(within(fsp).getByText("2 разряд · Продуктовое программирование")).toBeInTheDocument();
});

test("данные: ручная правка — ФИО, контакты и ссылки уходят одним PATCH", async () => {
  mount("/me/profile?tab=data");
  fireEvent.click(await screen.findByTestId("profile-data-edit"));
  fireEvent.change(screen.getByTestId("profile-data-fullname"), { target: { value: " Пётр Петров " } });
  fireEvent.change(screen.getByTestId("profile-data-email"), { target: { value: "petr@x.test" } });
  fireEvent.click(screen.getByTestId("profile-data-link-add"));
  fireEvent.change(screen.getByTestId("profile-data-link-0"), { target: { value: "github.com/petr" } });
  fireEvent.click(screen.getByTestId("profile-data-save"));
  expect(await screen.findByText("Ссылка должна начинаться с http:// или https://")).toBeInTheDocument();
  expect(calls).toHaveLength(0);
  fireEvent.change(screen.getByTestId("profile-data-link-0"), { target: { value: "https://github.com/petr" } });
  fireEvent.click(screen.getByTestId("profile-data-save"));
  await waitFor(() =>
    expect(calls[0]?.body).toEqual({ full_name: "Пётр Петров", contacts: { email: "petr@x.test", phone: null, telegram: null }, links: ["https://github.com/petr"] }),
  );
  expect(await screen.findByTestId("profile-data-saved")).toHaveTextContent("Данные сохранены.");
  expect(calls.some((c) => c.url.includes("/confirm"))).toBe(false); // без резюме опыт не подтверждаем
});

test("данные: «Заполнить из резюме» — разбор сразу виден в полях, сохранение подтверждает резюме", async () => {
  mount("/me/profile?tab=data");
  const file = new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" });
  fireEvent.change(await screen.findByTestId("profile-data-file"), { target: { files: [file] } });
  const draft = await screen.findByTestId("profile-data-draft");
  expect(draft).toHaveTextContent("Черновик из резюме");
  expect(draft).toHaveTextContent("навыков: 2");
  expect(screen.getByTestId("profile-data-fullname")).toHaveValue("Анна Резюмеева");
  expect(screen.getByTestId("profile-data-email")).toHaveValue("anna@cv.test");
  expect(screen.getByTestId("profile-data-link-0")).toHaveValue("https://github.com/anna-cv");
  expect(screen.queryByTestId("profile-data-link-1")).not.toBeInTheDocument(); // «не ссылка» отброшена
  expect(within(screen.getByTestId("profile-data-exp-0")).getByDisplayValue("Кедр Софт")).toBeInTheDocument();
  expect(within(screen.getByTestId("profile-data-edu-0")).getByDisplayValue("МГТУ")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("profile-data-save"));
  await waitFor(() => expect(calls.some((c) => c.url.endsWith("/resumes/r1/confirm"))).toBe(true));
  expect(calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ full_name: "Анна Резюмеева", links: ["https://github.com/anna-cv"] });
  expect(calls.find((c) => c.url.endsWith("/confirm"))?.body).toMatchObject({
    edits: { experience: [{ company: "Кедр Софт", start: "2022-03" }], education: [{ institution: "МГТУ" }] },
  });
});

test("данные: незаконченный черновик (resume_draft_id) открывается после перезагрузки", async () => {
  profile = { ...full, resume_draft_id: "r1" };
  resume = { status: "parsed", parsed: parsedResume };
  mount("/me/profile?tab=data");
  expect(await screen.findByTestId("profile-data-draft")).toBeInTheDocument();
  expect(screen.getByTestId("profile-data-fullname")).toHaveValue("Анна Резюмеева");
});

test("/me/graph ведёт на вкладку «Граф» профиля", async () => {
  mount("/me/graph");
  expect(await screen.findByTestId("graph-view")).toBeInTheDocument();
  expect(screen.getByTestId("profile-tab-graph")).toHaveAttribute("data-state", "active");
});

test("ошибка загрузки профиля: сообщение и повтор", async () => {
  profile = undefined;
  vi.mocked(fetch).mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
    if (u.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
    return res(503, { code: "boom" });
  });
  mount("/me/profile");
  expect(await screen.findByRole("alert", {}, { timeout: 8000 })).toHaveTextContent("Не загрузилось");
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  expect(screen.queryByTestId("profile-tabs")).not.toBeInTheDocument();
}, 15000);

test("пустой профиль: «Доказательств пока нет», одна кнопка, вкладка «Данные» доступна", async () => {
  profile = { ...base, claimed_soft: [], category: null, skills: [], team_signals: [], grade: { grade: null, score: null, confidence: null, preliminary: true, breakdown: [] } };
  mount("/me/profile");
  expect(await screen.findByText("Доказательств пока нет")).toBeInTheDocument();
  expect(screen.getByTestId("profile-empty-action")).toHaveAttribute("href", "/me/assessment");
  expect(screen.getByTestId("profile-tab-data")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Почему такой грейд" })).not.toBeInTheDocument();
});

test("доказательства навыка: название, источник, дата", async () => {
  mount("/me/skills/python");
  expect(await screen.findByText("Кубок ФСП, финал, 2 место из 120")).toBeInTheDocument();
  expect(within(screen.getByRole("main")).getByText("ФСП")).toBeInTheDocument();
  expect(screen.getByText("проверено")).toBeInTheDocument();
});

test("чужой/несуществующий навык: сообщение, не падение", async () => {
  mount("/me/skills/nope");
  expect(await screen.findByRole("alert")).toHaveTextContent("Такого навыка нет в вашем профиле");
});
