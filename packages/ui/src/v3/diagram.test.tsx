import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Diagram, DIAGRAM_MAX_SCALE, DIAGRAM_MIN_SCALE, DIAGRAM_VIEW0, diagramWheelFactor, diagramZoomAt } from "./diagram";
import { Markdown } from "./content";

const render_ = vi.fn(async (_id: string, code: string) => {
  if (code.includes("BROKEN")) throw new Error("Parse error");
  return { svg: '<svg data-testid="svg" width="100" height="50"><text>схема</text></svg>' };
});
vi.mock("mermaid", () => ({ default: { initialize: vi.fn(), render: (id: string, code: string) => render_(id, code) } }));

const FENCE = "```";

describe("diagramZoomAt / diagramWheelFactor", () => {
  it("точка под курсором остаётся на месте", () => {
    const v = diagramZoomAt({ scale: 1, x: 10, y: -5 }, 2, 40, 20);
    expect(v.scale).toBe(2);
    // экранная точка (px - x)/scale неизменна
    expect((40 - v.x) / v.scale).toBeCloseTo((40 - 10) / 1);
    expect((20 - v.y) / v.scale).toBeCloseTo((20 + 5) / 1);
  });
  it("масштаб ограничен", () => {
    expect(diagramZoomAt(DIAGRAM_VIEW0, 1000, 0, 0).scale).toBe(DIAGRAM_MAX_SCALE);
    expect(diagramZoomAt(DIAGRAM_VIEW0, 0.0001, 0, 0).scale).toBe(DIAGRAM_MIN_SCALE);
  });
  it("колесо вверх приближает, вниз отдаляет", () => {
    expect(diagramWheelFactor(-100)).toBeGreaterThan(1);
    expect(diagramWheelFactor(100)).toBeLessThan(1);
  });
});

describe("Diagram", () => {
  it("рисует svg и открывает полноэкранный просмотр с кнопками масштаба", async () => {
    render(<Diagram code={"flowchart LR\n A --> B"} label="Схема сервиса" />);
    const card = await screen.findByTestId("diagram");
    expect(card.querySelector("svg")).not.toBeNull();
    fireEvent.click(card);
    expect(await screen.findByTestId("diagram-viewer")).toBeInTheDocument();
    expect(screen.getByTestId("diagram-scale")).toHaveTextContent("100%");
    fireEvent.click(screen.getByRole("button", { name: "Увеличить" }));
    expect(screen.getByTestId("diagram-scale")).toHaveTextContent("130%");
    fireEvent.click(screen.getByRole("button", { name: "Сбросить масштаб" }));
    expect(screen.getByTestId("diagram-scale")).toHaveTextContent("100%");
  });

  it("колесо меняет масштаб, перетаскивание сдвигает", async () => {
    render(<Diagram code={"flowchart LR\n A --> B"} />);
    fireEvent.click(await screen.findByTestId("diagram"));
    const area = await screen.findByTestId("diagram-viewer");
    fireEvent.wheel(area, { deltaY: -120, clientX: 5, clientY: 5 });
    await waitFor(() => expect(screen.getByTestId("diagram-scale").textContent).not.toBe("100%"));
    const canvas = screen.getByTestId("diagram-viewer-canvas");
    const shift = () => /translate\((-?[\d.]+)px, (-?[\d.]+)px\)/.exec(canvas.style.transform.replace("translate(-50%, -50%)", ""))!.slice(1).map(Number);
    const [x0, y0] = shift();
    // jsdom без PointerEvent: имитируем MouseEvent с нужным типом и pointerId.
    const ptr = (type: string, x: number, y: number) =>
      fireEvent(area, Object.assign(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y }), { pointerId: 1 }));
    ptr("pointerdown", 10, 10);
    ptr("pointermove", 40, 25);
    ptr("pointerup", 40, 25);
    const [x1, y1] = shift();
    expect(x1! - x0!).toBeCloseTo(30);
    expect(y1! - y0!).toBeCloseTo(15);
  });

  it("ошибка разбора — исходный текст, без падения", async () => {
    render(<Diagram code="BROKEN" />);
    expect(await screen.findByTestId("diagram-error")).toHaveTextContent("BROKEN");
  });
});

describe("Markdown + mermaid", () => {
  it("блок mermaid становится схемой, остальной код остаётся кодом", async () => {
    render(<Markdown>{`Текст\n\n${FENCE}mermaid\nflowchart LR\n A --> B\n${FENCE}\n\n${FENCE}sql\nSELECT 1;\n${FENCE}`}</Markdown>);
    expect(await screen.findByTestId("diagram")).toBeInTheDocument();
    expect(screen.getByText("SELECT 1;")).toBeInTheDocument();
  });
});
