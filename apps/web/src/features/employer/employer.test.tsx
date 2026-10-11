import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const vac = {
  id: "v1", company_id: "c1", title: "Backend (Python)", role: "backend", grade_min: "middle", grade_max: "middle_plus",
  formats: ["remote"], employment_type: "full", city: null, salary_from: 200000, salary_to: 280000, range_too_wide: false,
  description: null, status: "published", important_qualities: [], skills: [{ slug: "python", required: true, min_level: 2, weight: 1 }],
  version: 1, created_at: "2026-10-01T00:00:00Z", published_at: "2026-10-01T00:00:00Z",
};
const card = {
  pseudo_id: "p1", pseudonym: "Candidate #1", avatar_seed: "abc", primary_role: "backend", grade: "middle", grade_preliminary: false,
  primary_stack: ["python"], top_skills: [{ slug: "python", name: "Python", level: 3, sources: ["fsp"] }], fsp_highlights: [],
  salary_min: 200000, formats: ["remote"], city: "Москва", relocation: false, search_status: "active",
  match: { score: 0.82, explanation: [{ kind: "plus", code: "skill_confirmed", text: "Python подтверждён кодом", skill: "python", evidence_ids: [], weight: 0.3 }] },
  updated_at: "2026-10-02T00:00:00Z",
};
const bodies: unknown[] = [];
const feedback: unknown[] = [];
const parsed = {
  filters: { roles: ["backend"], skills_must: [{ slug: "python" }], formats: ["remote"], salary_max: 220000, semantic_text: "высоконагруженный api" },
  chips: [
    { key: "roles", value: "backend", label: "Роль: Backend", source: "rule", confidence: 0.85 },
    { key: "skills_must", value: { slug: "python" }, label: "Навык: Python", source: "rule", confidence: 0.9 },
    { key: "formats", value: "remote", label: "Формат: Удалённо", source: "rule", confidence: 0.9 },
    { key: "salary_max", value: 220000, label: "Бюджет: до 220 000 ₽", source: "rule", confidence: 0.9 },
    { key: "semantic_text", value: "высоконагруженный api", label: "Смысл: высоконагруженный api", source: "rule", confidence: 0.5 },
  ],
  unparsed: [],
  refining: false,
};

beforeEach(() => {
  bodies.length = 0;
  feedback.length = 0;
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      if (url.includes("/vacancies")) return res(200, [vac]);
      if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "python", name: "Python" }] });
      if (url.endsWith("/recs/feedback")) {
        feedback.push(JSON.parse(String(init?.body)));
        return res(200, {});
      }
      if (url.endsWith("/search/parse")) return res(200, parsed);
      if (url.includes("/search/candidates")) {
        bodies.push(JSON.parse(String(init?.body)));
        return res(200, { items: [card], next_cursor: null, total: 1, session_id: "s1" });
      }
      if (url.includes("/candidates/p1/card")) {
        return res(200, { ...card, skills: [{ skill: { slug: "python", name: "Python", group: "language" }, confidence: 0.8, level: 3, sources: ["fsp"], claimed_only: false, status: "active", top_evidence: [{ id: "e1", source: "fsp", strength: 0.9, observed_at: "2026-01-10", title: "Кубок ФСП, финал", verified: true }] }], grade_info: { grade: "middle", score: 6, confidence: 0.7, preliminary: false, breakdown: [] }, experience: [], offers_from_you: [] });
      }
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

test("подборка под вакансию: запрос с vacancy_id, match-ring и объяснение", async () => {
  mount("/employer/vacancies/v1/shortlist");
  const tile = await screen.findByRole("article", { name: "Candidate #1" });
  expect(within(tile).getByRole("img", { name: "Совпадение 82 процентов" })).toBeInTheDocument();
  expect(within(tile).getByText("Python подтверждён кодом")).toBeInTheDocument();
  expect(bodies.at(-1)).toMatchObject({ vacancy_id: "v1", sort: "mutual", filters: { roles: ["backend"], grade_min: "middle", grade_max: "middle_plus" } });
});

test("свободный поиск: галочка формата попадает в запрос", async () => {
  mount("/employer/search");
  await screen.findByRole("article", { name: "Candidate #1" });
  fireEvent.click(screen.getByRole("checkbox", { name: "Удалённо" }));
  await vi.waitFor(() => expect(bodies.at(-1)).toMatchObject({ filters: { formats: ["remote"] }, vacancy_id: null }));
});

test("текст превращается в чипсы и фильтры, крестик убирает условие", async () => {
  mount("/employer/search");
  await screen.findByRole("article", { name: "Candidate #1" });
  fireEvent.change(screen.getByRole("searchbox", { name: "Кого ищете" }), { target: { value: "бэкендер на Python, highload, удалёнка, до 220 тыс" } });
  fireEvent.click(screen.getByRole("button", { name: "Найти" }));
  const chips = await screen.findByRole("list", { name: "Распознано" });
  expect(within(chips).getByText("Python")).toBeInTheDocument();
  expect(within(chips).getByText(/высоконагруженный api/)).toBeInTheDocument();
  await vi.waitFor(() =>
    expect(bodies.at(-1)).toMatchObject({
      filters: { roles: ["backend"], skills_must: [{ slug: "python" }], formats: ["remote"], salary_max: 220000, semantic_text: "высоконагруженный api" },
    }),
  );
  expect(screen.getByRole("checkbox", { name: "Удалённо" })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(within(chips).getByRole("button", { name: "Убрать условие «Python»" }));
  await vi.waitFor(() => expect((bodies.at(-1) as { filters: object }).filters).not.toHaveProperty("skills_must"));
  expect(within(screen.getByRole("list", { name: "Распознано" })).queryByText("Python")).toBeNull();
});

test("реакции на карточку: шорт-лист и «Не подходит» уходят в /recs/feedback", async () => {
  mount("/employer/search");
  const tile = await screen.findByRole("article", { name: "Candidate #1" });
  fireEvent.click(within(tile).getByRole("button", { name: "В шорт-лист" }));
  expect(within(tile).getByRole("button", { name: "В шорт-лист" })).toHaveAttribute("aria-pressed", "true");
  await vi.waitFor(() => expect(feedback.at(-1)).toEqual({ session_id: "s1", candidate_pseudo_id: "p1", event: "shortlist" }));
  fireEvent.click(within(tile).getByRole("button", { name: "Не подходит" }));
  await vi.waitFor(() => expect(feedback.at(-1)).toMatchObject({ event: "dismiss" }));
  expect(screen.queryByRole("article", { name: "Candidate #1" })).toBeNull();
});

test("карточка кандидата: навыки и доказательства", async () => {
  mount("/employer/candidates/p1?vacancy=v1&source=match");
  expect(await screen.findByRole("heading", { name: "Backend #1" })).toBeInTheDocument();
  expect(await screen.findByText(/Кубок ФСП, финал/)).toBeInTheDocument();
});

test("карточка кандидата: обе темы, навыки без повторов, заявленные в своей колонке", async () => {
  const base = (await (fetch as unknown as (u: string) => Promise<Response>)("/candidates/p1/card").then((r) => r.json())) as typeof card & { skills: unknown[] };
  const py = base.skills[0] as Record<string, unknown>;
  const claimed = { ...py, skill: { slug: "redis", name: "Redis", group: "db" }, claimed_only: true, level: 0, sources: ["resume"], top_evidence: [] };
  const f = fetch as unknown as ReturnType<typeof vi.fn>;
  const prev = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) =>
    url.includes("/candidates/p1/card")
      ? res(200, { ...base, skills: [py, { ...py }, claimed, { ...claimed }], fsp_highlights: [{ title: "Кубок", level: "national", place: 2, of: 40, year: 2025 }, { title: "Кубок", level: "national", place: 2, of: 40, year: 2025 }] })
      : prev(url, init),
  );
  const { container } = render(
    <MemoryRouter initialEntries={["/employer/candidates/p1"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "Backend #1" });
  expect(container.querySelector('[data-theme-scope="dark"]')).toBeNull();
  const tags = [...screen.getByRole("region", { name: "Навыки" }).querySelectorAll("[data-state]")].filter((e) => e.textContent?.startsWith("Python"));
  expect(tags).toHaveLength(1);
  expect(within(screen.getByRole("region", { name: "Заявлено кандидатом" })).getByText("Redis")).toBeInTheDocument();
  expect(screen.getAllByText(/Кубок · всероссийский этап/)).toHaveLength(1);
});

test("интерес кандидата, переключатель сортировки и кнопка «Приглашение»", async () => {
  const f = fetch as unknown as ReturnType<typeof vi.fn>;
  const prev = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.includes("/search/candidates")) {
      bodies.push(JSON.parse(String(init?.body)));
      const items = Array.from({ length: 6 }, (_, i) => ({ ...card, pseudo_id: `p${i + 1}`, pseudonym: `Backend #${i + 1}`, match: { ...card.match, interest: "high" } }));
      return res(200, { items, next_cursor: null, total: 6, session_id: "s1" });
    }
    return prev(url, init);
  });
  mount("/employer/vacancies/v1/shortlist");
  const first = await screen.findByRole("article", { name: "Backend #1" });
  expect(within(first).getByText("Интерес кандидата: высокий")).toBeInTheDocument();
  // обоснование открыто у первых пяти, у шестого свёрнуто
  expect(within(first).getByText("Почему подходит")).toBeInTheDocument();
  const sixth = screen.getByRole("article", { name: "Backend #6" });
  expect(within(sixth).queryByText("Почему подходит")).toBeNull();
  fireEvent.click(within(sixth).getByRole("button", { name: "Показать обоснование: Backend #6" }));
  expect(within(sixth).getByText("Почему подходит")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Только по соответствию" }));
  await vi.waitFor(() => expect(bodies.at(-1)).toMatchObject({ sort: "match", vacancy_id: "v1" }));
  fireEvent.click(within(first).getByRole("button", { name: "Приглашение" }));
  await vi.waitFor(() => expect(feedback.at(-1)).toMatchObject({ candidate_pseudo_id: "p1", event: "shortlist" }));
});

test("список вакансий строками, из строки — в подборку", async () => {
  mount("/employer/vacancies");
  const list = await screen.findByRole("list", { name: "Вакансии" });
  expect(within(list).getByText("Backend (Python)")).toBeInTheDocument();
  expect(within(list).getByRole("link", { name: "Подборка" })).toHaveAttribute("href", "/employer/vacancies/v1/shortlist");
});

function stubCard(status: number, extra?: Record<string, unknown>) {
  const f = fetch as unknown as ReturnType<typeof vi.fn>;
  const prev = f.getMockImplementation()!;
  f.mockImplementation(async (url: string, init?: RequestInit) => {
    if (url.includes("/candidates/p1/card")) {
      if (status !== 200) return res(status, { code: "x", status });
      const base = (await prev(url, init).then((r: Response) => r.json())) as Record<string, unknown>;
      return res(200, { ...base, ...extra });
    }
    return prev(url, init);
  });
}

test("карточка кандидата: заявлено и подтверждено, анонимный опыт, шорт-лист по need_id", async () => {
  stubCard(200, {
    categories: [{ profession: "backend", grade: "junior" }],
    claimed_vs_confirmed: [{ profession: "backend", declared_grade: "middle", confirmed_grade: "junior", status: "overclaimed" }],
    strength: { value: 0.64, rank: 0.3, top: [] },
  });
  mount("/employer/candidates/p1?source=match&need_id=n1");
  const panel = await screen.findByRole("region", { name: "Заявлено и подтверждено" });
  expect(within(panel).getByRole("region", { name: "Заявлено кандидатом" })).toBeInTheDocument();
  expect(within(panel).getByRole("region", { name: "Подтверждено" })).toBeInTheDocument();
  expect(screen.getByText("скрыто приватностью")).toBeInTheDocument();
  const crumb = screen.getByRole("navigation", { name: "Навигация" });
  expect(within(crumb).getByRole("link", { name: /Junior/ })).toHaveAttribute("href", "/employer/categories/backend/junior?need_id=n1");
  expect(screen.getByRole("button", { name: "В шорт-лист" })).toBeInTheDocument();
});

test("карточка кандидата: профиль скрыт (404) — пустое состояние со ссылкой назад", async () => {
  stubCard(404);
  mount("/employer/candidates/p1");
  expect(await screen.findByText("Профиль недоступен — кандидат скрыл его")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "К подбору" })).toHaveAttribute("href", "/employer");
});

test("карточка кандидата: ошибка 503 с кодом и «Повторить»", async () => {
  stubCard(503);
  mount("/employer/candidates/p1");
  expect(await screen.findByText("Не загрузилось")).toBeInTheDocument();
  expect(screen.getByText("ошибка 503")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
});

test("карточка кандидата: топ-10 навыков, «Все навыки» с поиском и фильтром, счётчики колонок", async () => {
  const skill = (n: number, claimed: boolean) => ({
    skill: { slug: `s${n}`, name: `Навык${n}`, group: "tools" },
    confidence: 0.5,
    level: 2,
    sources: [claimed ? "resume" : "fsp"],
    claimed_only: claimed,
    status: "active",
    top_evidence: [],
  });
  stubCard(200, { skills: Array.from({ length: 12 }, (_, i) => skill(i + 1, i >= 9)) });
  mount("/employer/candidates/p1");
  const skills = await screen.findByRole("region", { name: "Навыки" });
  expect(within(skills).getAllByText(/^Навык[0-9]+$/)).toHaveLength(10);
  expect(within(skills).queryByText("Навык12")).toBeNull();
  const cols = screen.getByRole("region", { name: "Заявлено и подтверждено" });
  expect(within(within(cols).getByRole("region", { name: "Подтверждено" })).getByLabelText("9 навыков")).toBeInTheDocument();
  expect(within(within(cols).getByRole("region", { name: "Заявлено кандидатом" })).getByLabelText("3 навыков")).toBeInTheDocument();
  fireEvent.click(within(skills).getByRole("button", { name: "Все навыки (12)" }));
  expect(within(skills).getByText("Навык12")).toBeInTheDocument();
  fireEvent.change(within(skills).getByRole("searchbox", { name: "Найти навык" }), { target: { value: "навык11" } });
  expect(within(skills).getByText("Навык11")).toBeInTheDocument();
  expect(within(skills).queryByText("Навык12")).toBeNull();
  fireEvent.change(within(skills).getByRole("searchbox", { name: "Найти навык" }), { target: { value: "" } });
  fireEvent.click(within(skills).getByRole("radio", { name: "Подтверждённые" }));
  expect(within(skills).queryByText("Навык12")).toBeNull();
  expect(within(skills).getByText("Навык1")).toBeInTheDocument();
});
