import { render, screen } from "@testing-library/react";

import { MatchRing, SkillChip, TrustDots, constellationPoints } from ".";

test("TrustDots подписывает уровень и вид", () => {
  render(<TrustDots level={3} kind="claimed" />);
  expect(screen.getByRole("img", { name: "Уровень 3 из 4, только из резюме" })).toBeInTheDocument();
});

test("SkillChip для нового навыка помечен", () => {
  render(<SkillChip name="Rust" level={1} variant="provisional" />);
  expect(screen.getByText("НОВЫЙ")).toBeInTheDocument();
});

test("MatchRing ограничивает значение", () => {
  render(<MatchRing value={140} />);
  expect(screen.getByRole("img", { name: "Совпадение 100 процентов" })).toBeInTheDocument();
});

test("созвездие детерминировано и содержит 5–8 узлов", () => {
  const a = constellationPoints("Backend #42");
  expect(a).toEqual(constellationPoints("Backend #42"));
  expect(a.length).toBeGreaterThanOrEqual(5);
  expect(a.length).toBeLessThanOrEqual(8);
  expect(a).not.toEqual(constellationPoints("Backend #43"));
});
