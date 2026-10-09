import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { TEMPLATES, sampleStem, stepErrors } from "./guide-model";
import { buildSpec, initialForm } from "./model";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];

beforeEach(() => {
  calls.length = 0;
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || (url.endsWith("/me") && !url.includes("/companies"))) return res(200, { id: "u1", email: "o@b.ru", role: "employer", consents: ["pd_processing"] });
      if (url.includes("/taxonomy")) return res(200, { skills: [{ slug: "system_design", name: "Проектирование систем", kind: "hard" }] });
      if (url.endsWith("/families") && method === "POST")
        return res(201, {
          id: "f9", slug: "c-1", title: "Т", kind: "exact", source: "spec", skill: "system_design", skill_type: "hard", level: 3,
          status: "draft", key_status: "approved", form: {}, author_form: {}, key_draft: null, autocheck: { ok: true, seeds: 200 }, examples: [],
        });
      if (url.includes("/employer/tasks")) return res(200, []);
      return res(404, { code: "not_found" });
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

describe("E39-27 модель", () => {
  test("все шаблоны проходят локальную проверку и собираются в спек", () => {
    expect(TEMPLATES.map((t) => t.id)).toEqual(["backend", "frontend", "ai"]);
    for (const t of TEMPLATES) {
      expect(stepErrors(t.form, 5)).toEqual({});
      expect(buildSpec(t.form).skill).toBeTruthy();
    }
  });
  test("шаг 1 требует название и навык, шаг 3 — условие", () => {
    expect(Object.keys(stepErrors(initialForm(), 1))).toEqual(["title", "skill"]);
    expect(Object.keys(stepErrors(initialForm(), 3))).toEqual(["stem"]);
    expect(stepErrors(initialForm(), 2)).toEqual({});
  });
  test("предпросмотр подставляет первые значения переменных", () => {
    expect(sampleStem(TEMPLATES[0]!.form)).toContain("50 запросов");
    expect(sampleStem(TEMPLATES[0]!.form)).toContain("20 мс");
  });
});

describe("E39-27 мастер", () => {
  test("задание по шаблону сохраняется за 5 шагов", async () => {
    mount("/employer/families/guide");
    await screen.findByTestId("guide-page");
    fireEvent.click(screen.getByTestId("guide-tpl-backend"));
    expect(screen.getByTestId("guide-candidate-stem")).toHaveTextContent("50 запросов");
    let clicks = 0;
    for (let i = 0; i < 4; i++) {
      fireEvent.click(screen.getByTestId("guide-next"));
      clicks++;
      expect(await screen.findByTestId(`guide-step-${i + 2}`)).toHaveAttribute("aria-current", "step");
    }
    fireEvent.click(screen.getByTestId("guide-save"));
    clicks++;
    expect(await screen.findByTestId("constructor-preview")).toBeInTheDocument();
    expect(clicks).toBeLessThanOrEqual(5 + 1);
    const post = calls.find((c) => c.method === "POST" && c.url.endsWith("/families"));
    expect(post?.body).toMatchObject({ kind: "exact", skill: "system_design", answer: "rps * ms / 1000" });
  });

  test("с нуля: пустое название не пускает дальше шага 1", async () => {
    mount("/employer/families/guide");
    fireEvent.click(await screen.findByTestId("guide-next"));
    expect(await screen.findByText(/Укажите название/)).toBeInTheDocument();
    expect(screen.getByTestId("guide-step-1")).toHaveAttribute("aria-current", "step");
  });

  test("шаг 3 показывает хороший и плохой пример", async () => {
    mount("/employer/families/guide");
    fireEvent.click(await screen.findByTestId("guide-tpl-frontend"));
    fireEvent.click(screen.getByTestId("guide-next"));
    fireEvent.click(await screen.findByTestId("guide-kind-find_bug"));
    fireEvent.click(screen.getByTestId("guide-next"));
    expect(await screen.findByTestId("guide-examples")).toHaveTextContent("Плохое задание");
  });

  test("пустое состояние /employer/tasks ведёт в мастер", async () => {
    mount("/employer/tasks");
    expect(await screen.findByTestId("tasks-empty-guide")).toHaveAttribute("href", "/employer/families/guide");
    expect(screen.getByTestId("tasks-howto")).toBeInTheDocument();
  });
});
