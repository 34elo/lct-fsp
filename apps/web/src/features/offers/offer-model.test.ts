import { canSendOffer, declineBreakdown, funnelOf, funnelSpanDays, groupDigits, isWideRange, lastActive, parseRub, rangeProblem, sortOffers } from "./offer-model";

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

describe("воронка приглашений", () => {
  const o = (status: string, created_at = "2026-10-01T00:00:00Z", extra: Record<string, unknown> = {}) => ({ status, created_at, ...extra });
  test("шаги накопительные, прямые приглашения идут сразу в «приглашение»", () => {
    const list = [
      o("interest", undefined, { interest_at: "2026-10-01T00:00:00Z" }),
      o("interest_opened", undefined, { interest_at: "2026-10-01T00:00:00Z", interest_opened_at: "2026-10-02T00:00:00Z" }),
      o("accepted", undefined, { interest_at: "2026-10-01T00:00:00Z", interest_opened_at: "2026-10-02T00:00:00Z", invited_at: "2026-10-03T00:00:00Z" }),
      o("sent"),
    ];
    expect(funnelOf(list)).toEqual({ interest: 3, opened: 2, invited: 2, accepted: 1 });
    expect(funnelOf([])).toEqual({ interest: 0, opened: 0, invited: 0, accepted: 0 });
  });
  test("период воронки в днях", () => {
    const now = Date.parse("2026-10-09T00:00:00Z");
    expect(funnelSpanDays([o("sent"), o("sent", "2026-10-05T00:00:00Z")], now)).toBe(8);
    expect(funnelSpanDays([], now)).toBe(0);
  });
  test("порядок: сначала то, что ждёт работодателя, и «Ответить» по свежему принятому", () => {
    const list = [o("sent", "2026-10-04T00:00:00Z"), o("accepted", "2026-10-01T00:00:00Z"), o("interest_opened", "2026-10-02T00:00:00Z"), o("interview", "2026-10-03T00:00:00Z")];
    expect(sortOffers(list).map((x) => x.status)).toEqual(["interview", "interest_opened", "accepted", "sent"]);
    expect(lastActive(list)?.status).toBe("interview");
    expect(lastActive([o("sent")])).toBeUndefined();
  });
  test("причины отказов", () => {
    const list = [o("declined"), o("declined"), o("declined")].map((x, i) => ({ ...x, decline: { reason: i < 2 ? "wrong_stack" : "low_salary" } }));
    expect(declineBreakdown(list)).toEqual([
      { reason: "wrong_stack", count: 2, pct: 67 },
      { reason: "low_salary", count: 1, pct: 33 },
    ]);
  });
});
