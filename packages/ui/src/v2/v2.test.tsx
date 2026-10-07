import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  AccountMenu,
  ActivityHeatmap,
  AppBar,
  CandidateCardV2,
  CategoryCard,
  CodeLines,
  ErrorBlock,
  FeedEvent,
  FeedList,
  GradeScale,
  GradeTag,
  MeterBar,
  MetricTile,
  OfferCardV2,
  OptionRow,
  QueryBar,
  ScatterPlot,
  SkillConstellation,
  SkillTag,
  StatusTag,
  TabBar,
  TaskHeader,
  TypeBar,
  dotsText,
  formatTimer,
  heatLevel,
} from "..";

describe("v2: примитивы", () => {
  it("SkillTag: точки доверия и состояние заявлено", () => {
    render(<SkillTag name="Git" level={0} state="claimed" />);
    expect(screen.getByText("Git").closest("[data-state]")).toHaveAttribute("data-state", "claimed");
    expect(screen.getByLabelText("доверие 0 из 4")).toHaveTextContent("○○○○");
    expect(dotsText(3)).toBe("●●●○");
  });

  it("StatusTag и GradeTag: заявленный грейд — пунктир", () => {
    render(
      <>
        <GradeTag claimed>Middle</GradeTag>
        <StatusTag state="ok">проверена</StatusTag>
      </>,
    );
    expect(screen.getByText("Middle").className).toContain("border-dashed");
    expect(screen.getByText("проверена")).toHaveAttribute("data-state", "ok");
  });

  it("MeterBar: значение ограничено 0–100, тик порога", () => {
    const { container } = render(<MeterBar value={140} threshold={55} label="Хард" />);
    expect(screen.getByRole("meter", { name: "Хард" })).toHaveAttribute("aria-valuenow", "100");
    expect(container.querySelector("[data-threshold]")).toHaveStyle({ left: "55%" });
  });
});

describe("v2: графики", () => {
  it("MetricTile: метка, число, спарклайн", () => {
    const { container } = render(<MetricTile label="сила" value={64} trend={[10, 20, 15, 40]} />);
    expect(screen.getByText("сила")).toBeInTheDocument();
    expect(screen.getByText("64")).toBeInTheDocument();
    expect(container.querySelector("path")?.getAttribute("d")).toMatch(/^M0 /);
  });

  it("SkillConstellation: подпись перечисляет навыки, сильнейший первым", () => {
    render(
      <SkillConstellation
        nodes={[
          { name: "Git", level: 0, state: "claimed" },
          { name: "Python", level: 3 },
          { name: "REST", level: 1, state: "adjacent" },
        ]}
      />,
    );
    expect(screen.getByRole("img", { name: "Созвездие навыков: Python, Git, REST" })).toBeInTheDocument();
  });

  it("ScatterPlot: точка «ты» и порог", () => {
    render(<ScatterPlot label="Где ты среди своих" points={[{ x: 10, y: 20 }]} you={{ x: 64, y: 10 }} threshold={{ x: 72, label: "порог Middle" }} />);
    const svg = screen.getByRole("img", { name: "Где ты среди своих" });
    expect(within(svg as unknown as HTMLElement).getByText("порог Middle")).toBeInTheDocument();
    expect(svg.querySelector("[data-you]")).not.toBeNull();
  });

  it("ActivityHeatmap: уровни относительно максимума", () => {
    const { container } = render(<ActivityHeatmap label="Просмотры" values={[0, 1, 2, 4]} />);
    expect([...container.querySelectorAll("i")].map((i) => i.dataset.level)).toEqual(["0", "1", "2", "4"]);
    expect(heatLevel(3, 4)).toBe(3);
  });

  it("GradeScale: подпись с порогами и результатом", () => {
    render(<GradeScale value={42} error={5} />);
    expect(screen.getByRole("img", { name: /Middle от 55.*Результат 42/ })).toBeInTheDocument();
    expect(screen.getByText("±5")).toBeInTheDocument();
  });

  it("TypeBar: строка на тип", () => {
    render(<TypeBar threshold={55} items={[{ label: "Хард", value: 48 }, { label: "Софт", value: 66 }]} />);
    expect(screen.getAllByRole("meter")).toHaveLength(2);
    expect(screen.getByText("66")).toBeInTheDocument();
  });
});

describe("v2: карточки", () => {
  it("CategoryCard: ссылка, гистограмма, три метрики", () => {
    render(
      <CategoryCard
        href="/employer/categories/backend/middle"
        c={{ title: "Backend · Middle", histogram: [1, 3, 2], highlight: 1, stats: [{ value: 37, label: "человек" }, { value: "220 000", label: "медиана ₽" }, { value: "24 %", label: "с ФСП" }] }}
      />,
    );
    expect(screen.getByRole("link")).toHaveAttribute("href", "/employer/categories/backend/middle");
    expect(screen.getByText("медиана ₽")).toBeInTheDocument();
  });

  it("CandidateCardV2: псевдоним, грейд, открыть профиль", () => {
    const open = vi.fn();
    render(
      <CandidateCardV2
        onOpen={open}
        c={{ pseudonym: "Backend #3377", match: 94, grade: "Middle", confirmed: true, salary: "190–220 тыс. ₽", skills: [{ name: "Python", level: 3 }] }}
      />,
    );
    expect(screen.getByRole("article", { name: "Backend #3377" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Совпадение 94 %" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открыть профиль" }));
    expect(open).toHaveBeenCalled();
  });

  it("FeedEvent: время и текст в списке", () => {
    render(
      <FeedList>
        <FeedEvent time="10:12">Backend #4821 подтвердил Junior</FeedEvent>
      </FeedList>,
    );
    expect(screen.getByRole("list", { name: "Лента событий" })).toHaveTextContent("10:12Backend #4821 подтвердил Junior");
  });

  it("QueryBar: Enter отправляет непустой запрос", () => {
    const submit = vi.fn();
    function Demo() {
      const [v, setV] = useState("");
      return <QueryBar value={v} onChange={setV} onSubmit={submit} />;
    }
    render(<Demo />);
    fireEvent.submit(screen.getByRole("search"));
    expect(submit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("textbox", { name: "Кого вы ищете" }), { target: { value: " Backend, Middle " } });
    fireEvent.click(screen.getByRole("button", { name: "Подобрать" }));
    expect(submit).toHaveBeenCalledWith("Backend, Middle");
  });

  it("OfferCardV2: вилка, «почему ты», действия", () => {
    render(
      <OfferCardV2
        o={{ company: "Северный код", rating: "4.6 / 5", verified: true, salary: "150–220 тыс. ₽", salaryNote: "до НДФЛ", reasons: ["Финалист ФСП"] }}
        actions={<button type="button">Принять</button>}
      />,
    );
    const card = screen.getByRole("article", { name: "Северный код" });
    expect(card).toHaveTextContent("150–220 тыс. ₽");
    expect(card).toHaveTextContent("Финалист ФСП");
    expect(within(card).getByRole("button", { name: "Принять" })).toBeInTheDocument();
  });
});

describe("v2: тест", () => {
  it("TaskHeader и formatTimer", () => {
    render(<TaskHeader index={7} total={20} secondsLeft={161} />);
    expect(screen.getByRole("timer")).toHaveTextContent("02:41");
    expect(screen.getByLabelText("Задание 7 из 20")).toBeInTheDocument();
    expect(formatTimer(-3)).toBe("00:00");
  });

  it("OptionRow: choice — radio, клик по строке", () => {
    const pick = vi.fn();
    render(
      <OptionRow selected onClick={pick}>
        LEFT JOIN
      </OptionRow>,
    );
    const opt = screen.getByRole("radio", { name: "LEFT JOIN" });
    expect(opt).toHaveAttribute("aria-checked", "true");
    fireEvent.click(opt);
    expect(pick).toHaveBeenCalled();
  });

  it("CodeLines: выбор строки кликом", () => {
    const pick = vi.fn();
    render(<CodeLines lines={["def add(item, bucket=[]):", "    bucket.append(item)"]} selected={0} onSelect={pick} />);
    expect(screen.getByRole("radio", { name: "Строка 1" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "Строка 2" }));
    expect(pick).toHaveBeenCalledWith(1);
  });

  it("CodeLines: несколько строк и своя нумерация", () => {
    const pick = vi.fn();
    render(<CodeLines lines={["a", "b"]} start={5} selected={[1]} onSelect={pick} lineTestId={(n) => `l-${n}`} />);
    expect(screen.getByRole("button", { name: "Строка 6" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByTestId("l-5"));
    expect(pick).toHaveBeenCalledWith(0);
  });

  it("ErrorBlock: навык, суть, код и «Объясни ответ»", () => {
    const explain = vi.fn();
    render(<ErrorBlock skill="SQL" title="путаешь LEFT и INNER JOIN" code={"SELECT 1\nWHERE x"} marked={[1]} onExplain={explain} />);
    expect(screen.getByText("путаешь LEFT и INNER JOIN")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Объясни ответ" }));
    expect(explain).toHaveBeenCalled();
  });

  it("ErrorBlock: своё действие и разбор под кодом", () => {
    render(
      <ErrorBlock skill="Go" title="Задание 2" action={<button type="button">Своё</button>} onExplain={() => undefined}>
        <p>Разбор</p>
      </ErrorBlock>,
    );
    expect(screen.getByRole("button", { name: "Своё" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Объясни ответ" })).toBeNull();
    expect(screen.getByText("Разбор")).toBeInTheDocument();
  });
});

describe("v2: каркас", () => {
  const items = [
    { href: "/me", label: "Главная" },
    { href: "/me/offers", label: "Приглашения", count: 3 },
  ];

  it("AppBar: активный пункт и счётчик", () => {
    render(<AppBar items={items} isCurrent={(i) => i.href === "/me/offers"} />);
    const nav = screen.getByRole("navigation", { name: "Основное меню" });
    expect(within(nav).getByRole("link", { name: "Приглашения 3" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Главная" })).not.toHaveAttribute("aria-current");
  });

  it("TabBar: четыре колонки по числу пунктов", () => {
    render(<TabBar items={items} isCurrent={(i) => i.href === "/me"} navLabel="Разделы" />);
    expect(screen.getByRole("navigation", { name: "Разделы" }).style.gridTemplateColumns).toBe("repeat(2, minmax(0, 1fr))");
  });

  it("AccountMenu: кнопка аватара открывает пункты", async () => {
    const out = vi.fn();
    render(<AccountMenu letter="анна" items={[{ label: "Тема", hint: "светлая", onSelect: () => {} }, { label: "Выйти", separatorBefore: true, onSelect: out }]} />);
    const btn = screen.getByRole("button", { name: "Меню аккаунта" });
    expect(btn).toHaveTextContent("А");
    fireEvent.keyDown(btn, { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Выйти" }));
    expect(out).toHaveBeenCalled();
  });
});
