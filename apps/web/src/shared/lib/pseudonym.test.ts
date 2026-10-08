import { describe, expect, it } from "vitest";

import { displayPseudonym } from "./pseudonym";

describe("displayPseudonym", () => {
  it("заменяет нейтральный префикс на роль", () => {
    expect(displayPseudonym("Candidate #4821", "backend")).toBe("Backend #4821");
  });
  it("без роли — «Кандидат»", () => {
    expect(displayPseudonym("Candidate #4821")).toBe("Кандидат #4821");
  });
  it("осмысленный псевдоним не трогает", () => {
    expect(displayPseudonym("Backend #4821", "frontend")).toBe("Backend #4821");
  });
});
