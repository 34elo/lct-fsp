import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import Quality from "./Quality";
import { report } from "./report";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ code: "not_found" }), { status: 404 })));
});
afterEach(() => vi.unstubAllGlobals());

test("страница качества показывает цифры отчёта make metrics", async () => {
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter>
        <Quality />
      </MemoryRouter>
    </Providers>,
  );
  expect(screen.getByRole("heading", { name: "Качество" })).toBeInTheDocument();
  for (const r of report.rows) expect(screen.getByTestId(`val-${r.id}`)).toHaveTextContent(r.value_text);
  expect(screen.getByTestId("sum-green")).toHaveTextContent(String(report.summary.green));
  expect(screen.getByTestId("sum-red")).toHaveTextContent(String(report.summary.red));
  expect(await screen.findByText(/Пока нет событий/)).toBeInTheDocument();
});

test("в отчёте нет метрик без готовой строки значения", () => {
  expect(report.rows.length).toBeGreaterThan(0);
  for (const r of report.rows) {
    expect(r.value_text).toBeTruthy();
    expect(r.target_text).toBeTruthy();
  }
});
