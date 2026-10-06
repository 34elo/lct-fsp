import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import type { NavigatorOut } from "@/api/model";
import { setAccessToken } from "@/shared/lib/token";
import { pathSteps } from "./NavigatorPath";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const item = {
  skill: "docker",
  name: "Docker",
  current_level: 0,
  extra: 9,
  pct: 64,
  median_salary_delta: 20000,
  how_to_confirm: [
    { kind: "test", minutes: 15 },
    { kind: "fsp_competition", id: "c1", title: "Кубок ФСП", start_date: "2026-11-10" },
  ],
};
const nav: NavigatorOut = {
  target: { role: "backend", grade: "middle" },
  current_grade: { profession: "backend", grade: "junior_plus", valid_until: "2027-01-10", needs_confirmation: false },
  next_grade: { points_needed: 2, hints: ["Пройдите тест"] },
  test: { profession: "backend", grade: "middle", path: "/me/assessment?profession=backend&grade=middle" },
  skill_gaps: [
    { skill: "docker", name: "Docker", weight: 0.8, confidence: 0.1, testable: true },
    { skill: "redis", name: "Redis", weight: 0.5, confidence: 0.2, testable: true },
  ],
  competitions: [{ id: "c1", title: "Кубок ФСП", start_date: "2026-11-10", registration_url: "https://fsp.example/reg", skills: ["Docker"] }],
  uplift: [item],
} as NavigatorOut;
const uplift = { relevant_total: 14, base: 14, items: [item], combo: { skills: ["Docker", "Redis"], extra: 12, pct: 86 } };

function mount(navBody: unknown, navStatus = 200, upBody: unknown = uplift) {
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: ["pd_processing"] });
      if (url.endsWith("/candidates/me/navigator")) return res(navStatus, navBody);
      if (url.endsWith("/candidates/me/uplift")) return res(200, upBody);
      return res(404, { code: "not_found" });
    }),
  );
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter initialEntries={["/me/navigator"]}>
        <App />
      </MemoryRouter>
    </Providers>,
  );
}

describe("навигатор роста", () => {
  it("pathSteps: текущий грейд, пробелы, цель", () => {
    const steps = pathSteps(nav);
    expect(steps.map((s) => [s.id, s.state])).toEqual([
      ["current", "done"],
      ["gap-docker", "current"],
      ["gap-redis", "future"],
      ["next", "future"],
    ]);
    expect(steps[0].label).toContain("Junior+");
    expect(steps[3].label).toContain("Middle");
  });

  it("рисует путь, соревнования и uplift-карточку с переходом на тест", async () => {
    mount(nav);
    expect(await screen.findByRole("heading", { name: "Навигатор роста" })).toBeInTheDocument();
    const path = await screen.findByLabelText("Этапы");
    expect(within(path).getByText(/Redis/)).toBeInTheDocument();
    expect(screen.getByText("Кубок ФСП", { selector: "b" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Записаться" })).toHaveAttribute("href", "https://fsp.example/reg");
    expect(screen.getByRole("link", { name: "Пройти тест" })).toHaveAttribute("href", "/me/assessment?profession=backend&grade=middle");
    await waitFor(() => expect(screen.getByText("+64%")).toBeInTheDocument());
    expect(screen.getByText(/Вместе с Docker \+ Redis: \+86% вакансий/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Пройти тест" })).toBeInTheDocument();
  });

  it("пустой профиль: подсказка пройти опрос", async () => {
    mount({ skill_gaps: [], competitions: [], uplift: [] }, 200, { relevant_total: 0, base: 0, items: [], combo: null });
    expect(await screen.findByText("Пока нечего предложить")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Пройти опрос" })).toHaveAttribute("href", "/me/assessment");
  });

  it("403 без согласий: понятный текст", async () => {
    mount({ code: "consent_required", title: "x" }, 403);
    expect(await screen.findByText(/после согласий/, undefined, { timeout: 4000 })).toBeInTheDocument();
  });
});
