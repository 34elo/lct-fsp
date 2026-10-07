import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";

import Landing from "./Landing";
import { JuryPanel } from "./JuryPanel";

afterEach(() => vi.unstubAllEnvs());

describe("Landing", () => {
  it("кнопки жюри скрыты без VITE_JURY_MODE и видны с ним (E32-4b)", () => {
    const ui = (
      <Providers client={makeQueryClient()}><MemoryRouter>
        <Landing />
      </MemoryRouter></Providers>
    );
    const { unmount } = render(ui);
    expect(screen.queryByTestId("jury-entry")).toBeNull();
    unmount();
    vi.stubEnv("VITE_JURY_MODE", "true");
    render(ui);
    expect(screen.getByRole("button", { name: "Войти как кандидат" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти как работодатель" })).toBeInTheDocument();
    expect(screen.getByText(/экспресс-тест/)).toBeInTheDocument();
  });

  it("показывает hero, шаги и ссылки на регистрацию без счётчиков", () => {
    render(
      <Providers client={makeQueryClient()}><MemoryRouter>
        <Landing />
      </MemoryRouter></Providers>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Не резюме, а доказательства" })).toBeInTheDocument();
    expect(screen.getByText("Соберите профиль", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Я ищу работу" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Я ищу людей" })).toHaveAttribute("href", "/register");
    expect(screen.queryByText(/профилей/)).toBeNull();
  });
});

describe("JuryPanel", () => {
  it("рисует 5 шагов только в режиме жюри (E34-2)", () => {
    const ui = <MemoryRouter initialEntries={["/me"]}><JuryPanel /></MemoryRouter>;
    const { unmount } = render(ui);
    expect(screen.queryByTestId("jury-panel")).toBeNull();
    unmount();
    vi.stubEnv("VITE_JURY_MODE", "true");
    render(ui);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
  });
});
