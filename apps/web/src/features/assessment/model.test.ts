import { describe, expect, it } from "vitest";

import { cooldownDate, errorView } from "./text";
import { ApiError } from "@/api/mutator";
import {
  latestSurvey,
  lowerGrade,
  seScale,
  thresholdGrade,
  toScale,
  typeRows,
  addStack,
  chainSteps,
  formatClock,
  initialAnswer,
  isAnswered,
  missedAnswers,
  move,
  moveTo,
  parseListing,
  parseNumber,
  pathStep,
  salaryError,
  skillRows,
  toPayload,
  toggleLine,
  validUntil,
} from "./model";

describe("ответ по kind", () => {
  it("order/sjt стартуют с показанного порядка", () => {
    expect(initialAnswer({ kind: "order", stem: "", options: ["a", "b", "c"] })).toEqual([0, 1, 2]);
    expect(initialAnswer({ kind: "choice", stem: "" })).toBeNull();
  });
  it("estimate уходит числом, exact строкой, find_bug отсортированным списком", () => {
    expect(toPayload({ kind: "estimate", stem: "" }, "3 000 000")).toBe(3_000_000);
    expect(toPayload({ kind: "estimate", stem: "" }, "10^5")).toBe(100_000);
    expect(toPayload({ kind: "estimate", stem: "" }, "abc")).toBeNull();
    expect(toPayload({ kind: "exact", stem: "" }, " 18 ")).toBe("18");
    expect(toPayload({ kind: "find_bug", stem: "" }, [4, 2])).toEqual([2, 4]);
    expect(toPayload({ kind: "choice", stem: "" }, 0)).toBe(0);
  });
  it("isAnswered: choice с индексом 0 — это ответ", () => {
    expect(isAnswered({ kind: "choice", stem: "" }, 0)).toBe(true);
    expect(isAnswered({ kind: "choice", stem: "" }, null)).toBe(false);
    expect(isAnswered({ kind: "exact", stem: "" }, "  ")).toBe(false);
    expect(isAnswered({ kind: "find_bug", stem: "" }, [])).toBe(false);
  });
  it("parseNumber", () => {
    expect(parseNumber("1,5")).toBe(1.5);
    expect(parseNumber("")).toBeNull();
  });
});

describe("разбор стема и списки", () => {
  it("find_bug: листинг отделяется от условия", () => {
    const r = parseListing("Найдите ошибку.\n\n 1 | def f(x):\n 2 |     return x + 1");
    expect(r.prose).toBe("Найдите ошибку.");
    expect(r.lines).toEqual([
      { no: 1, text: "def f(x):" },
      { no: 2, text: "    return x + 1" },
    ]);
  });
  it("toggleLine и move", () => {
    expect(toggleLine([3], 1)).toEqual([1, 3]);
    expect(toggleLine([1, 3], 3)).toEqual([1]);
    expect(move([0, 1, 2], 0, -1)).toEqual([0, 1, 2]);
    expect(move([0, 1, 2], 0, 1)).toEqual([1, 0, 2]);
  });
  it("chainSteps отбрасывает мусор", () => {
    expect(chainSteps([{ kind: "choice", stem: "s", options: ["a"] }, 5, null])).toHaveLength(1);
    expect(chainSteps(undefined)).toEqual([]);
  });
});

describe("прочее", () => {
  it("таймер", () => {
    expect(formatClock(41)).toBe("0:41");
    expect(formatClock(-3)).toBe("0:00");
    expect(formatClock(125.2)).toBe("2:06");
  });
  it("by_skill: только корректные строки", () => {
    expect(skillRows([{ skill: "sql", items: 5, share: 0.6 }, { x: 1 }])).toEqual([{ skill: "sql", items: 5, share: 0.6 }]);
  });
  it("12 месяцев", () => {
    expect(validUntil("2026-10-06T10:00:00Z")?.slice(0, 10)).toBe("2027-10-06");
    expect(validUntil(null)).toBeNull();
  });
  it("стек", () => {
    expect(addStack(["python"], " Python ")).toEqual(["python"]);
    expect(addStack(["python"], "Redis")).toEqual(["python", "redis"]);
    expect(salaryError("300000", "200000")).toBe(true);
    expect(salaryError("", "200000")).toBe(false);
  });
});

describe("ошибки с машинным code", () => {
  it("cooldown берёт дату из первой строки detail", () => {
    expect(cooldownDate("2026-11-04T10:00:00+00:00 повтор грейда")).toBe("2026-11-04T10:00:00+00:00");
    const v = errorView(new ApiError(409, "cooldown", { detail: "2026-11-04T10:00:00+00:00 смена" }));
    expect(v.text).toContain("04.11.2026");
  });
  it("email_not_verified ведёт на /verify-email", () => {
    expect(errorView(new ApiError(403, "email_not_verified", {})).link?.to).toBe("/verify-email");
  });
  it("attempt_active ведёт к попытке", () => {
    expect(errorView(new ApiError(409, "attempt_active", { detail: "abc" })).link?.to).toBe("/me/assessment/attempts/abc");
  });
  it("404 и неизвестное", () => {
    expect(errorView(new ApiError(404, "not_found", {})).text).toBe("Попытка не найдена");
    expect(errorView(new Error("x")).text).toContain("не так");
  });
});

describe("missedAnswers", () => {
  it("берёт только корректные строки с неполным баллом, по порядку", () => {
    const rows = missedAnswers([
      { response_id: "b", seq: 3, skill: "sql", score: 0.5 },
      { response_id: "a", seq: 1, skill: "python", score: 0 },
      { response_id: "c", seq: 2, skill: "sql", score: 1 },
      { seq: 4, score: 0 },
      null,
    ]);
    expect(rows.map((r) => r.responseId)).toEqual(["a", "b"]);
    expect(missedAnswers(undefined)).toEqual([]);
  });
});

describe("перенос варианта на место (E38-4)", () => {
  it("moveTo переносит элемент, остальные сдвигаются", () => {
    expect(moveTo([0, 1, 2, 3], 0, 2)).toEqual([1, 2, 0, 3]);
    expect(moveTo([0, 1, 2, 3], 3, 1)).toEqual([0, 3, 1, 2]);
  });
  it("вне границ и на то же место — без изменений", () => {
    const l = [0, 1, 2];
    expect(moveTo(l, 1, 1)).toBe(l);
    expect(moveTo(l, 0, 5)).toBe(l);
  });
});

describe("путь кандидата (E35-2a)", () => {
  const a = (id: string, status: string) => ({ id, status });
  it("нет опроса → опрос", () => {
    expect(pathStep({ surveys: [], attempts: [] })).toEqual({ kind: "survey", to: "/me/assessment" });
  });
  it("опрос есть, теста нет (или брошен) → тест", () => {
    expect(pathStep({ surveys: [{}], attempts: [] })).toEqual({ kind: "test", to: "/me/assessment" });
    expect(pathStep({ surveys: [{}], attempts: [a("x", "abandoned")] })?.kind).toBe("test");
  });
  it("идёт попытка → продолжить её", () => {
    expect(pathStep({ surveys: [{}], attempts: [a("old", "failed"), a("a1", "active")] })).toEqual({
      kind: "continue",
      to: "/me/assessment/attempts/a1",
    });
  });
  it("тест завершён (сдан или нет) → баннера нет", () => {
    expect(pathStep({ surveys: [{}], attempts: [a("a1", "passed")] })).toBeNull();
    expect(pathStep({ surveys: [{}], attempts: [a("a1", "failed")] })).toBeNull();
  });
});

describe("результат v2: шкала 0–100 (E38-5)", () => {
  it("пороги θ ложатся на полосы GradeScale: −1 → 30, 0 → 55, 1 → 80; края обрезаются", () => {
    expect([toScale(-1), toScale(0), toScale(1)]).toEqual([30, 55, 80]);
    expect([toScale(-5), toScale(5), toScale(0.4)]).toEqual([0, 100, 65]);
    expect([seScale(0.2), seScale(null), seScale(0)]).toEqual([5, undefined, undefined]);
  });

  it("порог: подтверждён — следующий грейд, Senior — свой, не подтверждён — заявленный", () => {
    expect(thresholdGrade("junior", "junior")).toBe("middle");
    expect(thresholdGrade("senior", "senior")).toBe("senior");
    expect(thresholdGrade(null, "middle")).toBe("middle");
    expect([lowerGrade("middle"), lowerGrade("junior")]).toEqual(["junior", null]);
  });

  it("типы в порядке справочника, мусор отброшен; последний опрос по профессии", () => {
    expect(typeRows({ soft: 0, hard: -1, x: 1 } as Record<string, number>)).toEqual([
      { type: "hard", value: 30 },
      { type: "soft", value: 55 },
    ]);
    expect(typeRows(undefined)).toEqual([]);
    const s = [
      { id: "a", profession: "backend", created_at: "2026-01-01" },
      { id: "b", profession: "backend", created_at: "2026-02-01" },
      { id: "c", profession: "frontend", created_at: "2026-03-01" },
    ];
    expect(latestSurvey(s, "backend")?.id).toBe("b");
    expect(latestSurvey(s, "qa")).toBeNull();
  });
});
