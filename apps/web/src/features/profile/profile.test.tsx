import { render, screen, within } from "@testing-library/react";
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
let evidenceStatus = 200;

class NoES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("EventSource", NoES);
  profile = full;
  evidenceStatus = 200;
  setAccessToken(null);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.endsWith("/candidates/me/profile")) return res(200, profile);
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

test("профиль: категория, предварительный грейд, разбивка, навыки, командные сигналы", async () => {
  mount("/me/profile");
  expect(await screen.findByRole("heading", { name: "Backend #4821" })).toBeInTheDocument();
  expect(screen.getByText("Junior+ · Backend · Python")).toBeInTheDocument();
  expect(screen.getByText(/Предварительно.*уверенность 40%/)).toBeInTheDocument();
  const why = screen.getByRole("region", { name: "Почему такой грейд" });
  expect(within(why).getByText("Стаж")).toBeInTheDocument();
  expect(within(why).getByText("+3")).toBeInTheDocument();
  expect(within(why).getByText("4,5 → Junior+")).toBeInTheDocument();
  expect(within(why).getByText("Пройдите тест")).toBeInTheDocument();
  const skills = screen.getByRole("region", { name: "Навыки" });
  expect(within(skills).getByRole("link", { name: "Python: чем подтверждён" })).toHaveAttribute("href", "/me/skills/python");
  expect(within(skills).getByRole("img", { name: /только из резюме/ })).toBeInTheDocument();
  const team = screen.getByRole("region", { name: "Командные сигналы" });
  expect(within(team).getByText("Лидерство")).toBeInTheDocument();
  expect(within(team).getByText(/сильное подтверждение/)).toBeInTheDocument();
  expect(within(team).getByText("Капитан команды, 2026")).toBeInTheDocument();
  expect(within(team).getByText(/коммуникабельный/)).toBeInTheDocument();
});

test("профиль: достижения ФСП, разряд, опыт и меню кандидата", async () => {
  profile = {
    ...full,
    fsp: {
      verified: true,
      achievements: [{ fact_id: "f1", title: "Финал по продуктовому программированию", level: "national", place: 2, of: 40, year: 2026, team_role: "captain" }],
      ranks: [{ discipline: "product", rank: "rank_2" }],
    },
    experience: [{ title: "Backend-разработчик", company: "Кедр Софт", start: "2024-08-01", end: null, skills: [] }],
  };
  mount("/me/profile");
  const fsp = await screen.findByRole("region", { name: "Достижения ФСП" });
  expect(within(fsp).getByText(/Финал по продуктовому программированию/)).toBeInTheDocument();
  expect(within(fsp).getByRole("img", { name: "2 место, медаль" })).toBeInTheDocument();
  expect(within(fsp).getByText("2 из 40")).toBeInTheDocument();
  expect(within(fsp).getByText("2 разряд · Продуктовое программирование")).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Опыт" })).getByText(/Кедр Софт/)).toBeInTheDocument();
  // Меню (E35-1): шапка (десктоп) и нижняя панель — одни и те же четыре раздела.
  const [top, bottom] = screen.getAllByRole("navigation", { name: "Разделы" });
  expect(within(top).getByRole("link", { name: "Приглашения" })).toHaveAttribute("href", "/me/offers");
  expect(within(top).getByRole("link", { name: "Профиль" })).toHaveAttribute("href", "/me/profile");
  expect(within(bottom).getByRole("link", { name: "Приглашения" })).toHaveAttribute("href", "/me/offers");
  expect(within(bottom).getByRole("link", { name: "Тест и грейд" })).toHaveAttribute("href", "/me/assessment");
});

test("профиль: навыки по группам, чек-лист «что усилит», заявлено/подтверждено, PDF", async () => {
  profile = {
    ...full,
    claimed_vs_confirmed: [{ profession: "backend", declared_grade: "senior", confirmed_grade: "middle", status: "overclaimed" }],
  };
  mount("/me/profile");
  await screen.findByTestId("profile-page");
  expect(within(screen.getByTestId("profile-skill-group-language")).getByText("Python")).toBeInTheDocument();
  expect(screen.getByTestId("profile-skill-group-db")).toHaveTextContent("Redis");
  const strength = screen.getByTestId("profile-strength");
  expect(within(strength).getByTestId("profile-strength-fsp")).toHaveTextContent("есть");
  expect(within(strength).getByRole("link", { name: "добавить: GitHub" })).toHaveAttribute("href", "/onboarding");
  expect(within(screen.getByTestId("profile-claimed-backend")).getByText("тест ниже заявленного")).toBeInTheDocument();
  expect(screen.getByTestId("profile-pdf")).toBeInTheDocument();
  expect(screen.getByTestId("profile-graph-link")).toHaveAttribute("href", "/me/graph");
});

test("ошибка загрузки профиля: сообщение и повтор", async () => {
  profile = undefined;
  vi.mocked(fetch).mockImplementation(async (url: unknown) => {
    const u = String(url);
    if (u.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
    if (u.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
    return res(500, { code: "boom" });
  });
  mount("/me/profile");
  expect(await screen.findByRole("alert", {}, { timeout: 8000 })).toHaveTextContent("Не удалось загрузить профиль");
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
}, 15000);

test("пустой профиль: подсказка вместо грейда и навыков", async () => {
  profile = { ...base, claimed_soft: [], category: null, skills: [], team_signals: [], grade: { grade: null, score: null, confidence: null, preliminary: true, breakdown: [] } };
  mount("/me/profile");
  expect(await screen.findByText(/Категория и грейд появятся/)).toBeInTheDocument();
  expect(screen.getByText(/Пока нет навыков/)).toBeInTheDocument();
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
