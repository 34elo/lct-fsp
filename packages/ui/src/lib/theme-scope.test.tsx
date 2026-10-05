import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ThemeScope } from "./theme-scope";

describe("ThemeScope", () => {
  it("dark добавляет класс .dark только области", () => {
    const { container } = render(<ThemeScope dark>x</ThemeScope>);
    expect((container.firstChild as HTMLElement).classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
  it("без флагов тему не меняет", () => {
    const { container } = render(<ThemeScope>x</ThemeScope>);
    expect((container.firstChild as HTMLElement).classList.contains("dark")).toBe(false);
  });
});
