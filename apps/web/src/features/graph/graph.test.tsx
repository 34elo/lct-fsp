import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { buildModel } from "@/features/graph/layout";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const graph = {
  profile_version: 12,
  nodes: [
    { id: "cand", type: "candidate", label: "Backend #4821" },
    { id: "f:fsp:91", type: "fsp_result", label: "Кубок России, финал", date: "2025-04", verified: true },
    { id: "f:repo:7", type: "repo", label: "репозиторий · её кода 82%", date: "2026-08", verified: false },
    { id: "s:fastapi", type: "skill", label: "FastAPI", level: 3, confidence: 0.65 },
    { id: "s:python", type: "skill", label: "Python", level: 2, confidence: 0.54, derived_from: "s:fastapi" },
    { id: "s:redis", type: "skill", label: "Redis", level: 1, confidence: 0.2 },
    { id: "s:django", type: "skill", label: "Django", level: 0, ghost: true },
  ],
  edges: [
    { from: "cand", to: "f:fsp:91", type: "has_fact" },
    { from: "f:repo:7", to: "s:fastapi", type: "confirms", strength: 0.5 },
    { from: "f:fsp:91", to: "s:python", type: "confirms", strength: 0.9 },
    { from: "s:fastapi", to: "s:python", type: "parent", weight: 0.6 },
    { from: "s:fastapi", to: "s:django", type: "adjacent", weight: 0.6 },
  ],
  highlight: [{ requirement: "fastapi", path: ["vac", "s:fastapi", "cand", "f:repo:7"] }],
};
let respond: () => Response;
const urls: string[] = [];

class NoES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("EventSource", NoES);
  urls.length = 0;
  respond = () => res(200, graph);
  setAccessToken(null);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.includes("/candidates/me/graph")) {
        urls.push(url);
        return respond();
      }
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount(path = "/me/graph") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

test("раскладка: факты и навыки по колонкам, подсветка путей", () => {
  const m = buildModel(graph as never);
  expect(m.facts.map((p) => p.node.id)).toEqual(["f:fsp:91", "f:repo:7"]);
  expect(m.skills).toHaveLength(4);
  expect(m.confirms).toHaveLength(2);
  expect(m.relations.map((e) => e.type)).toEqual(["parent", "adjacent"]);
  expect(m.highlightedSkills.has("s:fastapi")).toBe(true);
  expect(m.highlightedPairs.has("f:repo:7|cand")).toBe(true);
});

test("граф: схема, рёбра, призрак и список-альтернатива", async () => {
  mount();
  expect(await screen.findByTestId("graph-svg")).toHaveAccessibleName(/факты слева подтверждают навыки/);
  expect(screen.getAllByTestId("graph-edge-confirms")).toHaveLength(2);
  expect(screen.getByTestId("graph-edge-parent")).toBeInTheDocument();
  expect(screen.getByTestId("graph-edge-adjacent")).toBeInTheDocument();
  const list = screen.getByTestId("graph-list");
  const fast = within(list).getByTestId("graph-skill-fastapi");
  expect(within(fast).getByText(/репозиторий · её кода 82%/)).toBeInTheDocument();
  expect(within(fast).getByText(/сила 50%/)).toBeInTheDocument();
  expect(within(fast).getByText(/Смежный: Django/)).toBeInTheDocument();
  expect(within(fast).getByText("под требование вакансии")).toBeInTheDocument();
  expect(within(fast).getByRole("link", { name: "FastAPI: чем подтверждён" })).toHaveAttribute("href", "/me/skills/fastapi");
  expect(fast).toHaveTextContent("Входит в: Python");
  expect(within(list).getByTestId("graph-skill-redis")).toHaveTextContent("заявлен, без подтверждений");
  const ghost = within(list).getByTestId("graph-skill-django");
  expect(ghost).toHaveTextContent("не найден в профиле");
  expect(within(ghost).queryByRole("link")).toBeNull();
});

test("фильтры меняют параметры запроса", async () => {
  mount();
  await screen.findByTestId("graph-root");
  expect(urls[0]).toMatch(/skills=top/);
  expect(urls[0]).toMatch(/depth=facts/);
  fireEvent.click(screen.getByTestId("graph-skills-all"));
  fireEvent.click(screen.getByTestId("graph-depth-competitions"));
  await waitFor(() => expect(urls.some((u) => /skills=all/.test(u) && /depth=competitions/.test(u))).toBe(true));
  expect(screen.getByTestId("graph-depth-competitions")).toHaveAttribute("aria-pressed", "true");
});

test("пустое состояние", async () => {
  respond = () => res(200, { profile_version: 1, nodes: [{ id: "cand", type: "candidate", label: "X" }], edges: [] });
  mount();
  const empty = await screen.findByTestId("graph-empty");
  expect(within(empty).getByText("Граф пока пуст")).toBeInTheDocument();
  expect(within(empty).getByRole("link", { name: "Заполнить профиль" })).toHaveAttribute("href", "/me/profile/edit");
});

test("загрузка и ошибка", async () => {
  respond = () => res(500, { code: "boom" });
  mount();
  expect(await screen.findByTestId("graph-loading")).toBeInTheDocument();
  expect(await screen.findByText("Не удалось загрузить граф")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Повторить" })).toBeInTheDocument();
});
