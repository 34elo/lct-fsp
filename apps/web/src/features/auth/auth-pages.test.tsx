import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const json = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const consent = (type: string, required = false) => ({
  type,
  required,
  granted: false,
  version: null,
  current_version: "v1",
  granted_at: null,
});

function install(consents: () => Response) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "t", user: { id: "u1", email: "a@b.ru", role: "candidate" } });
      if (url.endsWith("/me/consents")) return consents();
      if (url.endsWith("/me")) return json(200, { id: "u1", email: "a@b.ru", role: "candidate", consents: [] });
      return json(404);
    }),
  );
}

function mount(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

class FakeES {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("согласия: из API только обязательные, неизвестный тип не ломает экран", async () => {
  install(() => json(200, [consent("pd_processing", true), consent("profile_publication"), consent("brand_new_type", true)]));
  mount("/consents");
  expect(await screen.findByTestId("consents-item-pd_processing")).toHaveTextContent("обязательно");
  expect(screen.queryByTestId("consents-item-profile_publication")).toBeNull(); // необязательное — в настройках
  expect(screen.getByTestId("consents-item-brand_new_type")).toHaveTextContent("brand_new_type");
  expect(screen.getAllByRole("checkbox")).toHaveLength(2);
  expect(screen.getByTestId("consents-submit")).toBeDisabled();
});

test("согласия: пока грузятся — скелетон, не «Загрузка…»", async () => {
  install(() => new Promise<Response>(() => {}) as unknown as Response);
  mount("/consents");
  await screen.findByTestId("consents-form-loading");
  expect(screen.queryByText(/Загрузка…/)).toBeNull();
});

test("согласия: ошибка загрузки — ErrorState с повтором", async () => {
  let ok = false;
  install(() => (ok ? json(200, [consent("pd_processing", true)]) : json(500, { code: "boom" })));
  mount("/consents");
  expect(await screen.findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent("Не удалось загрузить согласия");
  ok = true;
  fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
  await waitFor(() => expect(screen.getByTestId("consents-item-pd_processing")).toBeInTheDocument());
});

test("вход и регистрация: поля и кнопки с data-testid, карточка 440 px", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => json(401)));
  const { unmount } = mount("/login");
  expect(await screen.findByTestId("auth-email")).toBeInTheDocument();
  expect(screen.getByTestId("auth-password")).toHaveAttribute("autocomplete", "current-password");
  expect(screen.getByTestId("auth-card").className).toContain("max-w-[440px]");
  unmount();

  mount("/register");
  fireEvent.click(await screen.findByTestId("auth-role-employer"));
  expect(screen.getByRole("radio", { name: /Я ищу людей/ })).toBeChecked();
  expect(screen.getByTestId("auth-password")).toHaveAttribute("minlength", "8");
});
