import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";

import Landing from "./Landing";
import { JuryPanel } from "./JuryPanel";


const STATS = { candidates: 1248, companies: 86, invitations: 3912, median_days_to_invite: 3 };

function stubStats(body: unknown, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body === undefined ? "" : JSON.stringify(body), { status })),
  );
}

beforeEach(() => stubStats(STATS));
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

function renderLanding() {
  return render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    </Providers>,
  );
}

describe("Landing", () => {
  it("«Демо для жюри» и вход жюри скрыты без VITE_JURY_MODE и видны с ним (E32-4b, T6)", () => {
    const { unmount } = renderLanding();
    expect(screen.queryByTestId("jury-entry")).toBeNull();
    expect(screen.queryByRole("link", { name: "Демо для жюри" })).toBeNull();
    unmount();
    vi.stubEnv("VITE_JURY_MODE", "true");
    renderLanding();
    expect(screen.getByRole("button", { name: "Войти как кандидат" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти как работодатель" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Демо для жюри" })).toHaveAttribute("href", "#jury");
    expect(screen.getByText(/экспресс-тест/)).toBeInTheDocument();
  });

  it("показывает заголовок hero и все блоки макета", async () => {
    renderLanding();
    expect(screen.getByRole("heading", { level: 1, name: "Тест вместо резюме. Компании приходят сами" })).toBeInTheDocument();
    expect(screen.getByText("Десять минут, подтверждённая категория и приглашения с вилкой.")).toBeInTheDocument();
    for (const name of [
      "Три шага для каждой стороны",
      "Четыре отличия, которые видно сразу",
      "Результаты соревнований ФСП поднимают тебя внутри категории",
      "Десять минут до первого приглашения",
    ]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
    expect(await screen.findByRole("heading", { level: 2, name: /Платформа в цифрах/ })).toBeInTheDocument();
    expect(screen.getByText("Бесплатно для кандидатов")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Войти" })).toHaveAttribute("href", "/login");
  });

  it("шаг 1 кандидата: все профессии открыты", () => {
    renderLanding();
    expect(screen.getByText("Backend, Frontend, AI Engineer и другие.")).toBeInTheDocument();
    expect(screen.queryByText(/Backend, Frontend или AI Engineer/)).toBeNull();
  });

  it("вкладки «Кандидату / Компании» переключаются кликом и стрелками (A4, A5)", () => {
    renderLanding();
    const candidate = screen.getByRole("tab", { name: "Кандидату" });
    const company = screen.getByRole("tab", { name: "Компании" });
    expect(candidate).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Кандидату" })).toBeVisible();
    fireEvent.click(company);
    expect(company).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Компании" })).toBeVisible();
    expect(screen.getByText("Опишите, кого ищете")).toBeVisible();
    fireEvent.keyDown(company, { key: "ArrowLeft" });
    expect(candidate).toHaveAttribute("aria-selected", "true");
    expect(candidate).toHaveFocus();
    fireEvent.keyDown(candidate, { key: "ArrowRight" });
    expect(company).toHaveAttribute("aria-selected", "true");
  });

  it("переключатель темы меняет тему страницы (A10)", () => {
    renderLanding();
    const before = document.documentElement.classList.contains("dark");
    fireEvent.click(screen.getByRole("button", { name: before ? "Светлая тема" : "Тёмная тема" }));
    expect(document.documentElement.classList.contains("dark")).toBe(!before);
    expect(screen.getByRole("button", { name: before ? "Тёмная тема" : "Светлая тема" })).toBeInTheDocument();
  });

  it("якорь шапки прокручивает к блоку, не меняя адрес (T4)", () => {
    const scrollTo = vi.fn();
    vi.stubGlobal("scrollTo", scrollTo);
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), addEventListener() {}, removeEventListener() {} }));
    renderLanding();
    fireEvent.click(screen.getByRole("link", { name: "Доверие" }));
    expect(scrollTo).toHaveBeenCalled();
    expect(window.location.hash).toBe("");
  });
});

describe("Цифры платформы (GET /public/stats)", () => {
  it("показывает счётчики с меткой «демо» и склонением", async () => {
    renderLanding();
    expect(await screen.findByLabelText(/^1\s248$/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^3\s912$/)).toBeInTheDocument();
    expect(screen.getByText("кандидатов")).toBeInTheDocument();
    expect(screen.getByText("компаний")).toBeInTheDocument();
    expect(screen.getByText("приглашений")).toBeInTheDocument();
    expect(screen.getByText("дня до первого приглашения")).toBeInTheDocument();
    expect(screen.getByText("демо")).toBeInTheDocument();
  });

  it("нет ответа: блок скрыт", async () => {
    stubStats({ code: "boom" }, 500);
    renderLanding();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("heading", { name: /Платформа в цифрах/ })).toBeNull();
    expect(screen.queryByText("кандидатов")).toBeNull();
  });

  it("пустые цифры (null) прячут свой счётчик, а если пусто всё, то и блок", async () => {
    stubStats({ candidates: 5, companies: null, invitations: null, median_days_to_invite: null });
    const { unmount } = renderLanding();
    expect(await screen.findByText("кандидатов")).toBeInTheDocument();
    expect(screen.queryByText("компаний")).toBeNull();
    unmount();
    stubStats({ candidates: null, companies: null, invitations: null, median_days_to_invite: null });
    renderLanding();
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByRole("heading", { name: /Платформа в цифрах/ })).toBeNull();
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
    fireEvent.click(screen.getAllByRole("link", { name })[0]);
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
    expect(go("Условия")).toBe("/terms|");
    cleanup();
    expect(go("Политика ПДн")).toBe("/privacy|");
    cleanup();
    render(<Providers client={makeQueryClient()}><MemoryRouter><Landing /></MemoryRouter></Providers>);
    expect(screen.getByRole("link", { name: "Контакты" })).toHaveAttribute("href", "mailto:career@fsp.example");
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
