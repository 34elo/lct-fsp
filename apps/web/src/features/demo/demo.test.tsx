import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
let exam: unknown;
let hints: unknown;

const world = (domain: string, title: string, company: string) => ({
  domain, domain_title: title, company, scale: 4, kind: "exact", stem: `Схема «${company}»`, options: null, time_limit_s: 180, services: ["a", "b"],
});

beforeEach(() => {
  exam = {
    report: { seed: 42, families: 300, ai_solvable_share: 0.4633, simulation: true, rows: [{ declared: "middle", flagged_share: 0.9, granted: { junior: 13, none: 6 } }] },
    bank: { families: 0, measured: 0, solved_by_llm: 0, top: [] },
  };
  hints = { updated_at: null, discipline_rules: [], profession_candidates: [] };
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "fsp_admin", consents: ["pd_processing"] });
      if (url.includes("/admin/demo/two-worlds"))
        return res(200, {
          family: "arch_blast_radius", skill: "system-design", level: 3, seed: 7, choices: ["arch_blast_radius", "sql_join_filter"], same_shape: true,
          worlds: [world("ecommerce", "e-commerce", "Корзинка"), world("fintech", "финтех", "Монетка")],
        });
      if (url.endsWith("/admin/demo/llm-exam")) return res(200, exam);
      if (url.endsWith("/admin/skills/hints")) return res(200, hints);
      if (url.endsWith("/admin/professions")) return res(200, [{ slug: "backend" }, { slug: "ai_engineer" }]);
      return res(404, { code: "not_found", status: 404, title: "x", type: "x" });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

describe("вау-экраны E34-3", () => {
  it("два мира: две компании и общая сложность", async () => {
    mount("/admin/demo/two-worlds");
    expect(await screen.findByTestId("demo-world-ecommerce")).toHaveTextContent("Корзинка");
    expect(screen.getByTestId("demo-world-fintech")).toHaveTextContent("Монетка");
    expect(screen.getByTestId("demo-same-shape")).toHaveTextContent("Сложность одна");
    expect(screen.getByTestId("demo-same-shape")).toHaveTextContent("уровень 3");
  });

  it("LLM сдаёт тест: цифры из отчёта и честная пометка «симуляция»", async () => {
    mount("/admin/demo/llm-exam");
    expect(await screen.findByTestId("demo-simulation")).toHaveTextContent("Симуляция");
    expect(screen.getByTestId("demo-ai-share")).toHaveTextContent("46%");
    expect(screen.getByTestId("demo-llm-row-middle")).toHaveTextContent("требует подтверждения: 90%");
    expect(screen.getByTestId("demo-llm-bank")).toHaveTextContent("не измерен");
  });

  it("LLM сдаёт тест: без отчёта цифр нет", async () => {
    exam = { report: null, bank: { families: 0, measured: 0, solved_by_llm: 0, top: [] } };
    mount("/admin/demo/llm-exam");
    expect(await screen.findByTestId("demo-no-report")).toHaveTextContent("make eval-assessment");
    expect(screen.queryByTestId("demo-ai-share")).toBeNull();
  });

  it("новая профессия: без настоящих кластеров показывается помеченная фикстура", async () => {
    mount("/admin/demo/new-profession");
    expect(await screen.findByTestId("demo-cluster-source")).toHaveTextContent("Демо-пример");
    expect(screen.getByTestId("demo-cluster-skills")).toHaveTextContent("unity");
    expect(await screen.findByTestId("demo-prof-count")).toHaveTextContent("сейчас: 2 · После создания: 3");
  });

  it("новая профессия: настоящий кластер из роста графа", async () => {
    hints = { updated_at: "2026-10-03T00:00:00+00:00", discipline_rules: [], profession_candidates: [{ skills: ["rust", "wasm"], support: 9, covered_by_professions: 0.2 }] };
    mount("/admin/demo/new-profession");
    expect(await screen.findByTestId("demo-cluster-source")).toHaveTextContent("taxonomy_hints");
    expect(screen.getByTestId("demo-cluster")).toHaveTextContent("у 9 кандидатов");
  });
});
