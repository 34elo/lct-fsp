import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { BottomNav } from "./BottomNav";
import { PageContainer } from "./PageContainer";
import { CANDIDATE_BOTTOM, initials } from "./shell-meta";
import { NAV } from "@/app/routes";
import { Providers, makeQueryClient } from "@/app/Providers";

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

test("счётчик офферов: у нового кандидата без офферов бейджа нет, свои отклики не считаются", async () => {
  const { offerCount } = await import("./Shell");
  expect(offerCount({ status: 200, data: [] })).toBeUndefined();
  expect(offerCount({ status: 403, data: [] })).toBeUndefined();
  expect(offerCount({ status: 200, data: [{ initiator: "candidate" }] })).toBeUndefined();
  expect(offerCount({ status: 200, data: [{ initiator: "company" }, { initiator: "candidate" }] })).toBe(1);
});

test("шапка: вкладки не раздувают страницу на 800–1000 px (внутренняя прокрутка, без переноса)", async () => {
  const { AppHeader } = await import("./AppHeader");
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter>
        <AppHeader nav={NAV.candidate} />
      </MemoryRouter>
    </Providers>,
  );
  const tabs = screen.getAllByRole("navigation", { name: "Разделы" })[0];
  expect(tabs.className).toContain("overflow-x-auto");
  expect(tabs.className).toContain("min-w-0");
  expect(within(tabs).getAllByRole("link")[0].className).toContain("shrink-0");
});
