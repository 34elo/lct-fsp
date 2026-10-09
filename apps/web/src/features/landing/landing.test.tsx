import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

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
    expect(screen.getByRole("link", { name: "Ищу сотрудников" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: /Демо для жюри/ })).toBeNull();
  });
});

function Where() {
  const loc = useLocation();
  const role = (loc.state as { role?: string } | null)?.role ?? "";
  return <p data-testid="where">{`${loc.pathname}|${role}`}</p>;
}

describe("Переходы лендинга (E39-34)", () => {
  function go(name: string) {
    render(
      <Providers client={makeQueryClient()}>
        <MemoryRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="*" element={<Where />} />
          </Routes>
        </MemoryRouter>
      </Providers>,
    );
    fireEvent.click(screen.getByRole("link", { name }));
    return screen.getByTestId("where").textContent;
  }

  it("«Пройти тест» → регистрация кандидата", () => {
    expect(go("Пройти тест")).toBe("/register|candidate");
  });
  it("«Ищу сотрудников» → регистрация компании", () => {
    expect(go("Ищу сотрудников")).toBe("/register|employer");
  });
  it("«Войти» → /login", () => {
    expect(go("Войти")).toBe("/login|");
  });
  it("подвал: документы и политика — на свои экраны, контакты — вымышленная почта", () => {
    expect(go("Документы")).toBe("/terms|");
    cleanup();
    expect(go("Политика ПДн")).toBe("/privacy|");
    cleanup();
    render(<Providers client={makeQueryClient()}><MemoryRouter><Landing /></MemoryRouter></Providers>);
    expect(screen.getByRole("link", { name: "Контакты" })).toHaveAttribute("href", "mailto:career@fsp.example");
    expect(screen.getByRole("link", { name: "О проекте" })).toHaveAttribute("href", "#steps");
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
