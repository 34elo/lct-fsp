import { boardStats, canSendOffer, columnOf, declineBreakdown, groupByColumn, groupDigits, isWideRange, parseRub, rangeProblem } from "./offer-model";

test("parseRub понимает разряды и пустоту", () => {
  expect(parseRub("230 000")).toBe(230000);
  expect(parseRub("230 000")).toBe(230000);
  expect(parseRub("")).toBeNull();
  expect(parseRub("abc")).toBeNull();
  expect(parseRub("0")).toBeNull();
});

test("groupDigits", () => {
  expect(groupDigits("230000")).toBe("230 000");
  expect(groupDigits("2a3")).toBe("23");
});

test("rangeProblem: без вилки и при «до < от»", () => {
  expect(rangeProblem(null, 100)).toBe("missing");
  expect(rangeProblem(100, null)).toBe("missing");
  expect(rangeProblem(200, 100)).toBe("inverted");
  expect(rangeProblem(100, 100)).toBeNull();
});

test("isWideRange: порог (до − от) / от > 0.5", () => {
  expect(isWideRange(200000, 300000)).toBe(false); // ровно 0.5
  expect(isWideRange(200000, 300001)).toBe(true);
  expect(isWideRange(null, 300000)).toBe(false);
});

test("canSendOffer: вилка и вакансия или название", () => {
  expect(canSendOffer({ lo: 1, hi: 2, vacancyId: "v", title: "" })).toBe(true);
  expect(canSendOffer({ lo: 1, hi: 2, vacancyId: "", title: " " })).toBe(false);
  expect(canSendOffer({ lo: 1, hi: 2, vacancyId: "", title: "Бэкенд" })).toBe(true);
  expect(canSendOffer({ lo: 3, hi: 2, vacancyId: "v", title: "" })).toBe(false);
});

describe("канбан офферов", () => {
  const o = (status: string, created_at = "2026-10-01T00:00:00Z", reason?: string) => ({ status, created_at, decline: reason ? { reason } : null });
  test("колонка по статусу: закрытые и неизвестные уходят в «Закрыто»", () => {
    expect(columnOf("viewed")).toBe("viewed");
    expect(columnOf("declined")).toBe("closed");
    expect(columnOf("not_hired")).toBe("closed");
    expect(columnOf("???")).toBe("closed");
  });
  test("счётчики равны числу карточек, пустые колонки остаются, новые выше", () => {
    const g = groupByColumn([o("sent", "2026-10-01T00:00:00Z"), o("sent", "2026-10-03T00:00:00Z"), o("declined"), o("expired")]);
    expect(Object.keys(g)).toHaveLength(6);
    expect(g.sent.map((x) => x.created_at)[0]).toBe("2026-10-03T00:00:00Z");
    expect(g.closed).toHaveLength(2);
    expect(g.hired).toEqual([]);
    expect(Object.values(g).reduce((n, l) => n + l.length, 0)).toBe(4);
  });
  test("сводка и причины отказов", () => {
    const list = [o("sent"), o("viewed"), o("accepted"), o("hired"), o("declined", undefined, "wrong_stack"), o("declined", undefined, "wrong_stack"), o("declined", undefined, "low_salary")];
    expect(boardStats(list)).toEqual({ total: 7, viewedPct: 86, accepted: 2, hired: 1 });
    expect(boardStats([]).viewedPct).toBeNull();
    expect(declineBreakdown(list)).toEqual([
      { reason: "wrong_stack", count: 2, pct: 67 },
      { reason: "low_salary", count: 1, pct: 33 },
    ]);
  });
});
