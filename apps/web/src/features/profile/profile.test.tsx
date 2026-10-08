import { render, screen, waitFor, within } from "@testing-library/react";
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
let profile: unknown = full;
let standing: unknown = null;
let evidenceStatus = 200;

class NoES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("EventSource", NoES);
  profile = full;
  evidenceStatus = 200;
  standing = null;
  setAccessToken(null);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.endsWith("/candidates/me/profile")) return res(200, profile);
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

test("профиль: подтверждено и заявлено раздельно, грейд, разбивка, командные сигналы", async () => {
  mount("/me/profile");
  expect(await screen.findByRole("heading", { name: "Профиль", level: 1 })).toBeInTheDocument();
  const confirmed = await screen.findByRole("region", { name: "Подтверждено" });
  const row = within(confirmed).getByRole("link", { name: "Python: чем подтверждён" });
  expect(row).toHaveAttribute("href", "/me/skills/python");
  expect(row).toHaveTextContent("●●●○");
  expect(row).toHaveTextContent("ФСП");
  const claimed = screen.getByRole("region", { name: "Заявлено" });
  expect(within(claimed).getByRole("link", { name: "Redis: чем подтверждён" })).toHaveTextContent("заявлено в резюме");
  expect(within(claimed).getByRole("link", { name: "Redis: чем подтверждён" })).toHaveTextContent("○○○○");
  const card = screen.getByTestId("profile-status-card");
  expect(within(card).getByTestId("profile-grade")).toHaveTextContent("Junior+ · Backend");
  expect(within(card).getByTestId("profile-grade-status")).toHaveTextContent("не подтверждён");
  expect(within(card).getByText(/Предварительно.*уверенность 40%/)).toBeInTheDocument();
  expect(within(card).getByTestId("profile-published")).toHaveTextContent("профиль опубликован");
  expect(screen.queryByRole("region", { name: "Почему такой грейд" })).not.toBeInTheDocument();
  const team = screen.getByRole("region", { name: "Командные сигналы" });
  expect(within(team).getByText("Лидерство")).toBeInTheDocument();
  expect(within(team).getByText(/сильное подтверждение/)).toBeInTheDocument();
  expect(within(team).getByText("Капитан команды, 2026")).toBeInTheDocument();
  expect(within(team).getByText(/коммуникабельный/)).toBeInTheDocument();
});

test("профиль: подтверждённый тестом грейд и метка «тест 07.10» у навыка", async () => {
  profile = {
    ...full,
    skills: [{ ...full.skills[0], sources: ["test", "fsp"], top_evidence: [{ ...ev, source: "test", observed_at: "2026-10-07" }] }],
  };
  standing = { profession: "backend", grade: "junior", mode: "express", confirmed_at: "2026-10-07T10:00:00Z" };
  mount("/me/profile");
  const card = await screen.findByTestId("profile-status-card");
  await waitFor(() => expect(within(card).getByTestId("profile-grade-status")).toHaveTextContent("подтверждён 07.10 · экспресс"));
  expect(within(card).getByTestId("profile-grade")).toHaveTextContent("Junior · Backend");
  expect(screen.getByRole("link", { name: "Python: чем подтверждён" })).toHaveTextContent("тест 07.10");
});

test("профиль: вкладки ведут на ФСП, резюме и граф, действие «Добавить доказательство»", async () => {
  mount("/me/profile");
  await screen.findByTestId("profile-tabs");
  const tabs = within(screen.getByTestId("profile-tabs"));
  expect(tabs.getByRole("link", { name: "Навыки" })).toHaveAttribute("aria-current", "page");
  expect(tabs.getByRole("link", { name: "ФСП" })).toHaveAttribute("href", "/me/profile?tab=fsp");
  expect(tabs.getByRole("link", { name: "Резюме" })).toHaveAttribute("href", "/me/profile?tab=resume");
  expect(tabs.getByRole("link", { name: "Граф" })).toHaveAttribute("href", "/me/profile?tab=graph");
  expect(screen.getByTestId("profile-add")).toHaveAttribute("href", "/onboarding");
  expect(screen.getByTestId("profile-pdf")).toBeInTheDocument();
  expect(screen.getByTestId("profile-edit-link")).toHaveAttribute("href", "/me/profile/edit");
  expect(within(screen.getByTestId("profile-strength")).getByRole("link", { name: "добавить: Тест" })).toHaveAttribute("href", "/me/assessment");
});

test("профиль: вкладка «ФСП» — достижения, разряд и меню кандидата", async () => {
  profile = {
    ...full,
    fsp: {
      verified: true,
      achievements: [{ fact_id: "f1", title: "Финал по продуктовому программированию", level: "national", place: 2, of: 40, year: 2026, team_role: "captain" }],
      ranks: [{ discipline: "product", rank: "rank_2" }],
    },
  };
  mount("/me/profile?tab=fsp");
  const fsp = await screen.findByRole("region", { name: "Достижения ФСП" });
  expect(within(fsp).getByText(/Финал по продуктовому программированию/)).toBeInTheDocument();
  expect(within(fsp).getByText("привязан")).toBeInTheDocument();
  expect(within(fsp).getByRole("img", { name: "2 место, медаль" })).toBeInTheDocument();
  expect(within(fsp).getByText("2 из 40")).toBeInTheDocument();
  expect(within(fsp).getByText("2 разряд · Продуктовое программирование")).toBeInTheDocument();
  expect(screen.getByTestId("profile-tab-fsp")).toHaveAttribute("aria-current", "page");
  // Меню (E35-1): шапка (десктоп) и нижняя панель — одни и те же четыре раздела.
  const [top, bottom] = screen.getAllByRole("navigation", { name: "Разделы" });
  expect(within(top).getByRole("link", { name: "Приглашения" })).toHaveAttribute("href", "/me/offers");
  expect(within(top).getByRole("link", { name: "Профиль" })).toHaveAttribute("href", "/me/profile");
  expect(within(bottom).getByRole("link", { name: "Тест и грейд" })).toHaveAttribute("href", "/me/assessment");
});

test("профиль: вкладка «Резюме» — город, ожидания, формат, опыт", async () => {
  profile = {
    ...full,
    preferences: { city: "Санкт-Петербург", salary_min: 70000, formats: ["remote", "hybrid"], employment_types: [], relocation: false },
    experience: [{ title: "Backend-разработчик", company: "Кедр Софт", start: "2024-08-01", end: null, skills: [] }],
  };
  mount("/me/profile?tab=resume");
  const card = await screen.findByRole("region", { name: "Резюме" });
  expect(within(card).getByText("Санкт-Петербург")).toBeInTheDocument();
  expect(within(card).getByText(/^от 70.000/)).toBeInTheDocument();
  expect(within(card).getByText("удалёнка или гибрид")).toBeInTheDocument();
  expect(within(card).getByText("не указан")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Опыт" })).getByText(/Кедр Софт/)).toBeInTheDocument();
});

test("/me/graph ведёт на вкладку «Граф» профиля", async () => {
  mount("/me/graph");
  expect(await screen.findByTestId("graph-view")).toBeInTheDocument();
  expect(screen.getByTestId("profile-tab-graph")).toHaveAttribute("aria-current", "page");
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

test("пустой профиль: «Доказательств пока нет» и одна кнопка", async () => {
  profile = { ...base, claimed_soft: [], category: null, skills: [], team_signals: [], grade: { grade: null, score: null, confidence: null, preliminary: true, breakdown: [] } };
  mount("/me/profile");
  expect(await screen.findByText("Доказательств пока нет")).toBeInTheDocument();
  expect(screen.getByTestId("profile-empty-action")).toHaveAttribute("href", "/onboarding");
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
