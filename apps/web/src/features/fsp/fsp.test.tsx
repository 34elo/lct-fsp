import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";
import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const calls: { url: string; method: string; body: unknown }[] = [];
let linked = false;
let linkReply: Response;

beforeEach(() => {
  calls.length = 0;
  linked = false;
  linkReply = res(200, { method: "code", masked_contact: "a***@example.test" });
  setAccessToken("t");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/candidates/me/fsp")) return res(200, { link: { linked, verified: linked }, achievements: [], ranks: [], teams: [] });
      if (url.endsWith("/fsp/link")) return linkReply.clone();
      if (url.endsWith("/fsp/verify")) {
        linked = true;
        return res(200, { verified: true });
      }
      return res(404);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  render(
    <MemoryRouter>
      <Providers client={makeQueryClient()}>
        <FspLinkPanel next="/me" />
      </Providers>
    </MemoryRouter>,
  );
}

test("ID участника → код → подтверждение", async () => {
  mount();
  fireEvent.click(await screen.findByText("Ввести ID участника или email"));
  fireEvent.change(screen.getByLabelText(/ID участника или email в ФСП/), { target: { value: "p-anya" } });
  fireEvent.click(screen.getByText("Получить код"));
  fireEvent.change(await screen.findByLabelText(/Код из сообщения/), { target: { value: "123456" } });
  fireEvent.click(screen.getByText("Подтвердить"));
  await waitFor(() => expect(calls.find((c) => c.url.endsWith("/fsp/verify"))?.body).toEqual({ code: "123456" }));
  expect(calls.find((c) => c.url.endsWith("/fsp/link"))?.body).toEqual({ participant_id: "p-anya", manual: false });
  expect(await screen.findByText("ФСП подтверждена")).toBeInTheDocument();
});

test("ошибка fsp_not_found показывается по-русски", async () => {
  linkReply = res(404, { code: "fsp_not_found" });
  mount();
  fireEvent.click(await screen.findByText("Ввести ID участника или email"));
  fireEvent.change(screen.getByLabelText(/ID участника или email в ФСП/), { target: { value: "zzz" } });
  fireEvent.click(screen.getByText("Получить код"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Не нашли участника");
});
