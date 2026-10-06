import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CandidateCard, OfferCard } from "./cards";
import { AcceptanceMeter, BuildLog, CircuitLine, MatchWhy, OFFER_STATUS_LABEL, SalaryRange, StatusBadge, UpliftCard, type OfferStatus } from "./match";
import { formatRub, formatRubRange, formatRubRangeShort } from "../lib/format";

describe("formatRub", () => {
  it("неразрывные пробелы", () => {
    expect(formatRub(230000)).toBe("230 000 ₽");
    expect(formatRubRange(200000, 250000)).toBe("200 000 – 250 000 ₽");
    expect(formatRubRangeShort(200000, 250000)).toBe("200–250 тыс. ₽");
  });
});

describe("MatchWhy", () => {
  it("иконка и текст-подпись для каждого вида", () => {
    render(
      <MatchWhy
        items={[
          { kind: "ok", text: "Python 4 из 4" },
          { kind: "warn", text: "Нет Kafka" },
          { kind: "no", text: "Не готов к офису" },
        ]}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByText("Подходит:")).toBeInTheDocument();
    expect(screen.getByText("Есть нюанс:")).toBeInTheDocument();
    expect(screen.getByText("Не подходит:")).toBeInTheDocument();
  });
});

describe("SalaryRange", () => {
  it("вилка и подпись", () => {
    render(<SalaryRange from={200000} to={250000} size="offer" label="Вилка в месяц" />);
    expect(screen.getByText("200 000 – 250 000 ₽")).toHaveClass("text-[30px]");
    expect(screen.getByText("Вилка в месяц")).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it.each(Object.keys(OFFER_STATUS_LABEL) as OfferStatus[])("статус %s — слово и иконка", (s) => {
    const { container } = render(<StatusBadge status={s} />);
    expect(screen.getByText(OFFER_STATUS_LABEL[s])).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });
  it("покрывает все одиннадцать статусов контракта", () => {
    expect(Object.keys(OFFER_STATUS_LABEL)).toHaveLength(11);
  });
});

describe("AcceptanceMeter", () => {
  it.each([
    ["low", "низкая"],
    ["medium", "средняя"],
    ["high", "высокая"],
  ] as const)("%s", (level, word) => {
    render(<AcceptanceMeter level={level} />);
    expect(screen.getByRole("img", { name: `Вероятность принятия: ${word}` })).toBeInTheDocument();
  });
});

describe("UpliftCard", () => {
  it("процент ограничен 100, кнопка по onConfirm", () => {
    const fn = vi.fn();
    render(<UpliftCard skill="Kafka" pct={140} hint="Пройдите тест" onConfirm={fn} />);
    fireEvent.click(screen.getByRole("button", { name: "Подтвердить навык" }));
    expect(fn).toHaveBeenCalledOnce();
    expect(screen.getByRole("img", { name: "Рост шансов на 140 процентов" }).firstElementChild).toHaveStyle({ width: "100%" });
  });
});

describe("CircuitLine", () => {
  it("текущий этап помечен, будущие подписаны", () => {
    render(
      <CircuitLine
        orientation="horizontal"
        steps={[
          { id: "a", label: "Резюме", state: "done" },
          { id: "b", label: "Тест", state: "current" },
          { id: "c", label: "Оффер", state: "future" },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("— впереди")).toBeInTheDocument();
  });
});

describe("BuildLog", () => {
  it("строки со статусами", () => {
    render(<BuildLog title="разбор резюме" lines={[{ id: "1", text: "Текст извлечён", state: "done" }, { id: "2", text: "Навыки", state: "active" }]} />);
    expect(screen.getByRole("log", { name: "разбор резюме" })).toBeInTheDocument();
    expect(screen.getByText("Текст извлечён")).toBeInTheDocument();
  });
});

const CAND = {
  number: 4821,
  role: "backend",
  grade: "Middle",
  stack: "Python",
  match: 92,
  skills: [{ name: "Python", level: 4 as const }],
  fsp: [{ discipline: "Алгоритмы", tournament: "Кубок России", place: 2, total: 40, year: 2025 }],
  expectations: ["от 230 000 ₽", "удалёнка"],
  why: [{ kind: "ok" as const, text: "Python 4 из 4" }],
};

describe("CandidateCard", () => {
  it("анонимный псевдоним, без ПДн, действия вызывают колбэки", () => {
    const on = { s: vi.fn(), r: vi.fn(), o: vi.fn() };
    render(<CandidateCard c={CAND} onShortlist={on.s} onReject={on.r} onOpen={on.o} />);
    expect(screen.getByRole("heading", { name: "Backend #4821" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Совпадение 92 процентов" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "В шорт-лист" }));
    fireEvent.click(screen.getByRole("button", { name: "Не подходит" }));
    fireEvent.click(screen.getByRole("button", { name: /Открыть профиль/ }));
    expect(on.s).toHaveBeenCalledOnce();
    expect(on.r).toHaveBeenCalledOnce();
    expect(on.o).toHaveBeenCalledOnce();
  });
  it("в шорт-листе кнопка нажата", () => {
    render(<CandidateCard c={CAND} shortlisted />);
    expect(screen.getByRole("button", { name: "В шорт-лист" })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("OfferCard", () => {
  it("вилка крупно, статус, предупреждение «ниже ожиданий»", () => {
    const fn = vi.fn();
    render(
      <OfferCard
        onOpen={fn}
        o={{ company: "Северный код", rating: 4.6, from: 200000, to: 250000, title: "Backend Python", status: "viewed", match: 88, deadline: "14 окт", belowExpectation: 230000, acceptance: "high" }}
      />,
    );
    expect(screen.getByText("Просмотрен")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Ниже ваших ожиданий (от 230 000 ₽)");
    expect(screen.getByText("200 000 – 250 000 ₽")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Открыть оффер" }));
    expect(fn).toHaveBeenCalledOnce();
  });
});
