import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const middle = {
  profession: "backend", title: "Backend", grade: "middle", affinity: 0.82, candidates: 5, median_salary: 220000, fsp_share: 0.24,
  matched_skills: ["Python", "Django"], named: false,
};
const junior = { ...middle, grade: "junior", affinity: 0.82, candidates: 2, median_salary: 120000, fsp_share: 0.23 };
const senior = { ...middle, grade: "senior", candidates: 0, median_salary: null, fsp_share: null };
const need = (id: string) => ({ id, text: null, filters: {}, skills: { python: 1 }, grades: ["middle"], shortlist: [], created_at: "2026-10-05T00:00:00Z", categories: [] });
const base = {
  avatar_seed: "x", primary_role: "backend", grade: "middle", grade_preliminary: false, primary_stack: ["python"],
  top_skills: [{ slug: "python", name: "Python", level: 3, sources: ["test"] }, { slug: "django", name: "Django", level: 2, sources: ["test"] }],
  fsp_highlights: [], salary_min: 200000, formats: ["remote"], city: null, relocation: false, search_status: "active",
  updated_at: "2026-10-02T00:00:00Z", categories: [{ profession: "backend", grade: "middle" }],
};
const cards = [1, 2, 3, 4, 5].map((i) => ({ ...base, pseudo_id: `p${i}`, pseudonym: `Backend #${i}00${i}`, match: { score: 1 - i / 20, explanation: [] } }));
const activity = {
  items: [{ id: "e1", kind: "interest_opened", at: new Date().toISOString(), candidate: { pseudo_id: "p1", pseudonym: "Backend #1001" }, link: "/employer/offers/o1" }],
};
const parsed = {
  filters: { skills_must: [{ slug: "python" }, { slug: "django" }], grade_min: "middle", grade_max: "middle" },
  chips: [
    { key: "skills_must", value: { slug: "python" }, label: "Навык: Python", source: "rule", confidence: 0.9 },
    { key: "skills_must", value: { slug: "django" }, label: "Навык: Django", source: "rule", confidence: 0.9 },
    { key: "grade_min", value: "middle", label: "Грейд: Middle", source: "rule", confidence: 0.9 },
  ],
  unparsed: [],
};

const calls: { method: string; url: string; body?: unknown }[] = [];
let lostNeed = false;

const posts = () => calls.filter((c) => c.method === "POST" && c.url.endsWith("/needs")).map((c) => c.body as { filters: Record<string, unknown> });

beforeEach(() => {
  calls.length = 0;
  lostNeed = false;
  localStorage.clear();
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"], company: { id: "co1", name: "Acme", status: "verified", role: "admin" } });
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ method, url, body });
      if (url.endsWith("/needs") && method === "POST") {
        const f = body.filters ?? {};
        if (!f.skills_must && !f.professions) return res(422, { type: "x", title: "x", status: 422, code: "need_empty" });
        return res(201, need(f.fsp_only ? "n2" : f.professions ? "n3" : "n1"));
      }
      if (url.includes("/needs/n1/categories")) return lostNeed ? res(404, { type: "x", title: "x", status: 404, code: "need_not_found" }) : res(200, { need_id: "n1", shortlist: [], categories: [middle, junior, senior] });
      if (url.includes("/needs/n2/categories")) return res(200, { need_id: "n2", shortlist: [], categories: [{ ...middle, candidates: 1 }] });
      if (url.includes("/needs/n3/categories")) return res(200, { need_id: "n3", shortlist: [], categories: [{ ...middle, named: true, matched_skills: [] }] });
      if (url.includes("/categories/backend/middle/candidates")) {
        if (url.includes("need_id=n2")) return res(200, { items: cards.slice(0, 1), next_cursor: null, total: 1, session_id: "s" });
        return res(200, { items: cards, next_cursor: null, total: 5, session_id: "s1" });
      }
      if (url.includes("/categories/backend/junior/candidates")) return res(200, { items: cards.slice(0, 2), next_cursor: null, total: 2, session_id: "s2" });
      if (url.includes("/search/parse")) return res(200, parsed);
      if (url.includes("/taxonomy/skills/suggest")) return res(200, [{ slug: "python", name: "Python", provisional: false }]);
      if (url.includes("/taxonomy/professions/suggest")) return res(200, [{ slug: "backend", title: "Backend" }, { slug: "ai_engineer", title: "AI Engineer" }]);
      if (url.endsWith("/taxonomy")) return res(200, { version: 1, skills: [{ slug: "python", name: "Python" }, { slug: "django", name: "Django" }] });
      if (url.includes("/employer/activity")) return res(200, activity);
      if (url.endsWith("/subscriptions")) return res(200, []);
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

let location = "";
function Spy() {
  const l = useLocation();
  location = l.pathname + l.search;
  return null;
}

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
        <Spy />
      </Providers>
    </MemoryRouter>,
  );
}

const query = () => screen.findByRole("combobox", { name: "Кого вы ищете" });

test("первый вход: строка с тегами, примеры и лента; Подбор в меню", async () => {
  mount("/employer");
  expect(await query()).toHaveValue("");
  const examples = await screen.findByTestId("match-examples");
  expect(within(examples).getAllByRole("button")).toHaveLength(3);
  const feed = await screen.findByTestId("match-feed");
  expect(await within(feed).findByRole("link", { name: "Backend #1001" })).toHaveAttribute("href", "/employer/offers/o1");
  const nav = screen.getAllByRole("navigation", { name: "Разделы" })[0]!;
  expect(within(nav).getByRole("link", { name: "Подбор" })).toHaveAttribute("aria-current", "page");
  expect(posts()).toHaveLength(0);
});

test("«python django middle» → чипсы → категории с объяснением → компактные карточки; состояние в URL", async () => {
  mount("/employer");
  fireEvent.change(await query(), { target: { value: "python django middle" } });
  fireEvent.click(await screen.findByRole("option", { name: /Разобрать «python django middle»/ }));

  // чипсы навыков в строке, грейд — в условиях
  expect((await screen.findAllByTestId("query-chip-skill")).map((x) => x.textContent)).toEqual(["Python", "Django"]);
  expect(within(screen.getByTestId("match-chips")).getByText("Middle")).toBeInTheDocument();
  expect(calls.find((c) => c.url.includes("/search/parse"))?.body).toEqual({ text: "python django middle" });

  // потребность из условий, категории и «почему»
  const cats = await screen.findByTestId("match-categories");
  expect(posts()[0]).toEqual({ filters: { skills_must: [{ slug: "python" }, { slug: "django" }], grade_min: "middle", grade_max: "middle" } });
  expect(within(cats).getByRole("button", { name: /Backend · Middle/ })).toHaveAttribute("aria-pressed", "true");
  expect(within(cats).queryByRole("button", { name: /Backend · Senior/ })).not.toBeInTheDocument(); // пустая — по кнопке
  fireEvent.click(within(cats).getByRole("button", { name: "Ещё 1 без кандидатов" }));
  expect(within(cats).getByRole("button", { name: /Backend · Senior/ })).toBeInTheDocument();
  expect(within(screen.getByTestId("match-why")).getByText(/совпадают навыки: Python, Django · совпадение 82 %/)).toBeInTheDocument();
  expect(screen.getByTestId("match-why")).toHaveTextContent("Грейды — из запроса: Middle.");

  const top = await screen.findByTestId("match-top");
  expect(within(top).getAllByRole("article")).toHaveLength(5);
  const first = within(top).getByRole("link", { name: "Backend #1001: открыть профиль" });
  expect(first).toHaveAttribute("href", "/employer/candidates/p1?source=match");
  // компактная карточка: совпадение (без вакансии — rank), грейд, ожидания, топ-3 навыка
  expect(first).toHaveTextContent("Middle");
  expect(first).toHaveTextContent("от 200");
  expect(first).toHaveTextContent("Python");
  expect(location).toBe("/employer?skill=python&skill=django&grade=middle&need=n1");

  // выбор категории — в URL, кандидаты другой категории
  fireEvent.click(within(cats).getByRole("button", { name: /Backend · Junior/ }));
  expect(await screen.findByText("Кандидаты · Backend · Junior")).toBeInTheDocument();
  expect(within(await screen.findByTestId("match-top")).getAllByRole("article")).toHaveLength(2);
  expect(location).toContain("cat=backend%3Ajunior");
});

test("фильтр сужает выдачу: «Есть результаты ФСП» → новая потребность, меньше кандидатов; условие снимается крестиком", async () => {
  mount("/employer?skill=python&grade=middle&need=n1");
  expect(within(await screen.findByTestId("match-top")).getAllByRole("article")).toHaveLength(5);
  expect(posts()).toHaveLength(0); // потребность уже в ссылке

  fireEvent.click(within(screen.getAllByTestId("match-filters")[0]!).getByRole("checkbox", { name: "Есть результаты ФСП" }));
  expect(await screen.findByText("1 человек", undefined, { timeout: 3000 })).toBeInTheDocument();
  expect(posts().at(-1)!.filters).toMatchObject({ skills_must: [{ slug: "python" }], fsp_only: true });
  expect(within(await screen.findByTestId("match-top")).getAllByRole("article")).toHaveLength(1);
  expect(location).toBe("/employer?skill=python&grade=middle&fsp=1&need=n2");

  fireEvent.click(screen.getByRole("button", { name: "Убрать условие «Есть результаты ФСП»" }));
  expect(within(await screen.findByTestId("match-top")).getAllByRole("article")).toHaveLength(5);
});

test("подсказки системы: профессия и навык вставляются чипсами", async () => {
  mount("/employer");
  fireEvent.change(await query(), { target: { value: "back" } });
  const prof = await screen.findByRole("option", { name: /Backend.*профессия/ });
  fireEvent.click(prof);
  expect(await screen.findByTestId("query-chip-profession")).toHaveTextContent("Backend");
  expect(await screen.findByTestId("match-categories")).toBeInTheDocument();
  expect(posts().at(-1)).toEqual({ filters: { professions: ["backend"] } });
  expect(screen.getByTestId("match-why")).toHaveTextContent("Backend — выбрана в запросе");

  fireEvent.change(await query(), { target: { value: "pyt" } });
  fireEvent.click(await screen.findByRole("option", { name: /Python.*навык/ }));
  expect((await screen.findAllByTestId("query-chip-skill")).map((x) => x.textContent)).toEqual(["Python"]);
  await screen.findByTestId("match-categories");
  expect(posts().at(-1)).toEqual({ filters: { professions: ["backend"], skills_must: [{ slug: "python" }] } });
});

test("только фильтры без навыка и профессии — подсказка, потребность не создаётся", async () => {
  mount("/employer?grade=middle&fsp=1");
  expect(await screen.findByText("Добавьте навык или профессию — фильтры только сужают выдачу.")).toBeInTheDocument();
  expect(posts()).toHaveLength(0);
});

test("повторный вход: восстанавливаются условия последнего запроса", async () => {
  localStorage.setItem("fsp.employer.lastNeed", JSON.stringify({ id: "n1", text: "Python", chips: ["Python"], company: "co1", qs: "skill=python&grade=middle" }));
  mount("/employer");
  expect(await screen.findByTestId("match-categories")).toBeInTheDocument();
  expect(location).toBe("/employer?skill=python&grade=middle&need=n1");
  expect(posts()).toHaveLength(0);
});

test("запомненный запрос пропал — потребность строится заново", async () => {
  lostNeed = true;
  localStorage.setItem("fsp.employer.lastNeed", JSON.stringify({ id: "n1", text: "x", chips: [], company: "co1", qs: "skill=python&fsp=1" }));
  mount("/employer");
  // Цепочка: восстановление → 404 → новая потребность (с задержкой) → категории → кандидаты.
  expect(await screen.findByText("1 человек", undefined, { timeout: 4000 })).toBeInTheDocument();
  expect(location).toBe("/employer?skill=python&fsp=1&need=n2");
});
