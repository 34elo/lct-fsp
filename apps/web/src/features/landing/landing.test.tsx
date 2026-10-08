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
    expect(screen.getByRole("link", { name: "Демо для жюри →" })).toHaveAttribute("href", "#jury");
    expect(screen.getByText(/экспресс-тест/)).toBeInTheDocument();
  });

  it("показывает hero, три шага и ссылки на регистрацию без кнопки жюри", () => {
    render(
      <Providers client={makeQueryClient()}><MemoryRouter>
        <Landing />
      </MemoryRouter></Providers>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Тест подтверждает грейд. Работодатель приходит с вилкой." })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Три шага" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Пройти тест" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Найти специалиста" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: /Демо для жюри/ })).toBeNull();
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
