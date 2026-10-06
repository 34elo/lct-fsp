import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { BottomNav } from "./BottomNav";
import { PageContainer } from "./PageContainer";
import { CANDIDATE_BOTTOM, initials } from "./shell-meta";
import { NAV } from "@/app/routes";

test("нижняя навигация кандидата: четыре пункта с подписями и ссылками", () => {
  render(
    <MemoryRouter initialEntries={["/me/offers"]}>
      <BottomNav items={CANDIDATE_BOTTOM} all={NAV.candidate} />
    </MemoryRouter>,
  );
  const nav = screen.getByRole("navigation", { name: "Разделы" });
  expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Профиль", "Офферы", "Рост", "ФСП"]);
  expect(within(nav).getByRole("link", { name: "Офферы" })).toHaveAttribute("aria-current", "page");
  expect(within(nav).getByRole("link", { name: "Профиль" })).not.toHaveAttribute("aria-current");
});

test("PageContainer ограничивает ширину 1440", () => {
  render(<PageContainer as="main">x</PageContainer>);
  expect(screen.getByRole("main").className).toContain("max-w-[1440px]");
});

test("инициалы", () => {
  expect(initials("ivan.petrov@mail.ru")).toBe("IP");
  expect(initials("")).toBe("?");
});
