import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import Analytics from "@/features/admin/Analytics";
import { setAccessToken } from "@/shared/lib/token";

const day = (n: number, v: number | null) => ({ date: `2026-10-0${n}`, values: { registrations: v, tests: null } });
const body = {
  since: "2026-10-01T00:00:00Z",
  days: 30,
  min_cell: 5,
  funnel: [],
  fsp_share: { count: null, hidden: true, pct: null, of: null },
  navigator_to_competition: { count: null, hidden: true, pct: null, of: null },
  counters: [
    { id: "registrations", title: "Регистрации", count: 12, hidden: false },
    { id: "tests", title: "Пройденные тесты", count: null, hidden: true },
  ],
  daily: [day(1, 5), day(2, null), day(3, 7)],
};

beforeEach(() => {
  setAccessToken("t");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
});
afterEach(() => vi.unstubAllGlobals());

test("аналитика: счётчики, скрытые ячейки «< 5» и график по дням с подписанной осью", async () => {
  render(
    <MemoryRouter initialEntries={["/federation/analytics"]}>
      <Providers client={makeQueryClient()}>
        <Analytics />
      </Providers>
    </MemoryRouter>,
  );
  const reg = await screen.findByTestId("analytics-registrations");
  expect(reg).toHaveTextContent("12");
  expect(screen.getByTestId("analytics-tests")).toHaveTextContent("< 5");
  expect(screen.getByTestId("analytics-chart-registrations")).toHaveTextContent("День");
  expect(screen.queryByText(/Качество/)).toBeNull();
});
