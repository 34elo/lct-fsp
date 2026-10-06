import { canSendOffer, groupDigits, isWideRange, parseRub, rangeProblem } from "./offer-model";

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
