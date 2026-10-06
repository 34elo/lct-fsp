import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConstellationAvatar, SkillChip, TrustDots } from ".";
import { FspProtocol, GradeBadge, SectionLabel, TeamSignal, VerifiedMark, pseudonymLabel } from "./protocol";

describe("pseudonymLabel", () => {
  it("роль и номер", () => {
    expect(pseudonymLabel("backend", 4821)).toBe("Backend #4821");
    expect(pseudonymLabel("ml", "7")).toBe("ML #7");
    expect(pseudonymLabel("embedded", 1)).toBe("Embedded #1");
    expect(pseudonymLabel(null, 5)).toBe("Кандидат #5");
  });
});

describe("TrustDots с поповером", () => {
  it("без sources — просто картинка с подписью", () => {
    render(<TrustDots level={2} kind="inferred" />);
    expect(screen.getByRole("img", { name: "Уровень 2 из 4, предположительно" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });
  it("с sources — кнопка раскрывает источники, даты и силу", () => {
    render(
      <TrustDots
        level={3}
        skill="FastAPI"
        sources={[
          { title: "Код на GitHub", detail: "6 репозиториев", strength: "strong", date: "12 сен 2026" },
          { title: "Указано в резюме", strength: "none" },
        ]}
      />,
    );
    const t = screen.getByRole("button", { name: "Откуда навык FastAPI" });
    expect(t).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(t);
    expect(t).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Код на GitHub")).toBeInTheDocument();
    expect(screen.getByText("12 сен 2026")).toBeInTheDocument();
    expect(screen.getByText("сильно")).toBeInTheDocument();
    expect(screen.getByText("нет силы")).toBeInTheDocument();
  });
});

describe("SkillChip", () => {
  it.each(["verified", "claimed", "inferred", "adjacent", "provisional"] as const)("вариант %s рендерится с точками", (v) => {
    render(<SkillChip name="Python" level={2} variant={v} />);
    expect(screen.getByText("Python")).toBeInTheDocument();
    expect(screen.getByRole("img")).toBeInTheDocument();
  });
  it("метка «новый» по флагу isNew", () => {
    render(<SkillChip name="Go" isNew />);
    expect(screen.getByText("НОВЫЙ")).toBeInTheDocument();
  });
});

describe("GradeBadge", () => {
  it("собирает строку грейда", () => {
    render(<GradeBadge grade="Junior+" role="Backend" stack="Python" />);
    expect(screen.getByText("Junior+ · Backend · Python")).toBeInTheDocument();
    expect(screen.queryByText("предварительно")).toBeNull();
  });
  it("предварительный — пунктир и слово, не только вид", () => {
    render(<GradeBadge grade="Junior+" role="Backend" preliminary hint="Нужен тест" />);
    const el = screen.getByText("Junior+ · Backend").closest("span");
    expect(el).toHaveClass("border-dashed");
    expect(el).toHaveAttribute("title", "Нужен тест");
    expect(screen.getByText("предварительно")).toBeInTheDocument();
  });
});

describe("ConstellationAvatar", () => {
  it("красный узел только по signalNode, ровно один", () => {
    const { container, rerender } = render(<ConstellationAvatar seed="Backend #1" />);
    expect(container.querySelectorAll('circle[fill="var(--signal)"]')).toHaveLength(0);
    rerender(<ConstellationAvatar seed="Backend #1" signalNode />);
    expect(container.querySelectorAll('circle[fill="var(--signal)"]')).toHaveLength(1);
  });
});

describe("FspProtocol", () => {
  it("пустое состояние", () => {
    render(<FspProtocol results={[]} />);
    expect(screen.getByText("Результатов ФСП пока нет")).toBeInTheDocument();
  });
  it("строка протокола и медали 1/2/3", () => {
    render(
      <FspProtocol
        results={[
          { discipline: "Алгоритмы", tournament: "Кубок России", stage: "финал", place: 2, total: 40, role: "капитан", year: 2025 },
          { discipline: "Алгоритмы", tournament: "Открытая лига", stage: "этап 2", place: 17, total: 340, year: 2023 },
        ]}
      />,
    );
    expect(screen.getByRole("list", { name: "Протокол ФСП" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "2 место, медаль" })).toBeInTheDocument();
    expect(screen.getByText("2 из 40")).toBeInTheDocument();
    expect(screen.getByText(/Алгоритмы · Кубок России · финал/)).toHaveTextContent("капитан · 2025");
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });
});

describe("TeamSignal, SectionLabel, VerifiedMark", () => {
  it("сигнал со словами и фактом", () => {
    render(<TeamSignal name="Лидерство" strength="strong" fact="капитан на 2 соревнованиях ФСП" />);
    expect(screen.getByText(/сильное подтверждение/)).toBeInTheDocument();
    expect(screen.getByText("капитан на 2 соревнованиях ФСП")).toBeInTheDocument();
  });
  it("из резюме — не влияет на грейд", () => {
    render(<TeamSignal name="коммуникабельный" claimed />);
    expect(screen.getByText(/не влияет на грейд/)).toBeInTheDocument();
  });
  it("метка и плашка", () => {
    render(
      <>
        <SectionLabel>Уровень доверия</SectionLabel>
        <VerifiedMark />
      </>,
    );
    expect(screen.getByText("Уровень доверия")).toHaveClass("uppercase");
    expect(screen.getByText("Профиль подтверждён ФСП")).toBeInTheDocument();
  });
});
