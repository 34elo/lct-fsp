import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";
import { candTabOf, countBy, empTabOf, filterBy } from "./response-model";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const company = { id: "c1", name: "Север-Софт", verified: true };
const base = { created_at: "2026-10-05T10:00:00Z", expires_at: "2026-10-12T10:00:00Z", salary_from: 190000, salary_to: 230000, below_candidate_min: false, initiator: "candidate" };
const mine = [
  { ...base, id: "a1", status: "sent", company, vacancy: { id: "v1", title: "Python-разработчик (API)" } },
  { ...base, id: "a2", status: "interview", company: { ...company, name: "Лесков Лаб" }, vacancy: { id: "v2", title: "Backend-разработчик" } },
];
const cand = { pseudo_id: "p1", pseudonym: "Backend #4821", avatar_seed: "x", primary_role: "backend", grade: "middle" };
const theirs = [
  { ...base, id: "e1", status: "sent", vacancy: { id: "v1", title: "Python-разработчик (API)" }, candidate: cand },
  { ...base, id: "e2", status: "not_hired", vacancy: { id: "v1", title: "Python-разработчик (API)" }, candidate: { ...cand, pseudonym: "Backend #3077" } },
];
let role = "candidate";
const calls: string[] = [];

beforeEach(() => {
  setAccessToken(null);
  calls.length = 0;
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role, consents: ["pd_processing"] });
      if (url.includes("/candidates/me/applications/a1/withdraw")) {
        calls.push("withdraw");
        return res(200, { ...mine[0], status: "withdrawn" });
      }
      if (url.includes("/candidates/me/applications")) return res(200, mine);
      if (url.includes("/offers/e1/status")) {
        calls.push(String(init?.body));
        return res(200, theirs[0]);
      }
      if (url.includes("/offers?initiator=candidate")) return res(200, theirs);
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

test("вкладки: группировка статусов и счётчики", () => {
  expect(candTabOf("viewed")).toBe("waiting");
  expect(candTabOf("interview")).toBe("invited");
  expect(candTabOf("withdrawn")).toBe("closed");
  expect(empTabOf("sent")).toBe("new");
  expect(empTabOf("not_hired")).toBe("rejected");
  const items = [{ status: "sent" }, { status: "interview" }, { status: "declined" }];
  expect(countBy(items, candTabOf)).toEqual({ all: 3, waiting: 1, invited: 1, closed: 1 });
  expect(filterBy(items, "invited", candTabOf)).toHaveLength(1);
  expect(filterBy(items, "all", candTabOf)).toHaveLength(3);
});

test("кандидат: список откликов, фильтр и отзыв", async () => {
  role = "candidate";
  mount("/me/responses");
  expect(await screen.findByText("Север-Софт")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть приглашение" })).toHaveAttribute("href", "/me/offers/a2");
  fireEvent.click(screen.getByRole("button", { name: /Ждут ответа \(1\)/ }));
  expect(screen.queryByText("Лесков Лаб")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Отозвать отклик" }));
  await vi.waitFor(() => expect(calls).toContain("withdraw"));
});

test("работодатель: отклики, «Пригласить» ставит interview", async () => {
  role = "employer";
  mount("/employer/responses");
  expect(await screen.findByText("Backend #4821")).toBeInTheDocument();
  expect(screen.getByText("Backend #3077")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Пригласить" }));
  await vi.waitFor(() => expect(calls.some((c) => c.includes("interview"))).toBe(true));
});
