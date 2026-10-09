import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { hasTable, splitStem } from "./model";
import { Question } from "./Question";

const TABLE = "Выгрузка из базы «Рога»:\n\n`orders(id, status)`\n\n| id | status |\n| --- | --- |\n| 1 | new |\n| 2 | done |\n\nСколько заказов?";

describe("условие с таблицей (E39-9)", () => {
  it("hasTable видит GFM-таблицу и не путает с кодом", () => {
    expect(hasTable(TABLE)).toBe(true);
    expect(hasTable("print(1 | 2)\n\nx")).toBe(false);
    expect(splitStem(TABLE).code).toBeNull();
  });

  it("таблица рисуется таблицей, а не текстом", () => {
    render(<Question item={{ kind: "exact", stem: TABLE }} value="" onChange={() => {}} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("обычное условие — не жирное", () => {
    render(<Question item={{ kind: "estimate", stem: "Сколько запросов в секунду?" }} value="" onChange={() => {}} />);
    const stem = screen.getByTestId("assessment-stem");
    expect(stem.className).toContain("font-normal");
    expect(stem.className).not.toContain("font-semibold");
  });
});
