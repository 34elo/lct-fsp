import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Roadmap, type RoadmapStep } from "./roadmap";

const go = vi.fn();
const steps: RoadmapStep[] = [
  { id: "cur", kind: "current", state: "done", title: "Junior+", eyebrow: "Сейчас" },
  {
    id: "docker",
    kind: "skill",
    state: "current",
    title: "Docker",
    uplift: "+64% вакансий",
    actions: [
      { label: "Пройти задание", href: "/me/tasks", onClick: go },
      { label: "Соревнование ФСП", href: "https://fsp.example/reg", external: true },
    ],
  },
  { id: "goal", kind: "goal", state: "future", title: "Middle" },
];

describe("Roadmap", () => {
  it("рисует этапы по порядку, текущий помечен", () => {
    render(<Roadmap steps={steps} />);
    const items = within(screen.getByRole("region", { name: "Путь роста" })).getAllByRole("listitem");
    expect(items.map((i) => i.dataset.state)).toEqual(["done", "current", "future"]);
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("+64% вакансий")).toBeInTheDocument();
  });

  it("внутренняя ссылка идёт через onClick, внешняя открывается в новой вкладке", () => {
    render(<Roadmap steps={steps} />);
    fireEvent.click(screen.getByRole("link", { name: "Пройти задание" }));
    expect(go).toHaveBeenCalledTimes(1);
    const ext = screen.getByRole("link", { name: "Соревнование ФСП" });
    expect(ext).toHaveAttribute("target", "_blank");
    expect(ext).toHaveAttribute("href", "https://fsp.example/reg");
  });

  it("прокручивается по горизонтали", () => {
    render(<Roadmap steps={steps} />);
    expect(screen.getByTestId("roadmap").className).toContain("overflow-x-auto");
  });
});
