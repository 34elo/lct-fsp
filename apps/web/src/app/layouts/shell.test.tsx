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
  expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Главная", "Тест и грейд", "Вакансии", "Приглашения", "Профиль"]);
  expect(within(nav).getByRole("link", { name: "Приглашения" })).toHaveAttribute("aria-current", "page");
  expect(within(nav).getByRole("link", { name: "Главная" })).not.toHaveAttribute("aria-current");
});

test("PageContainer ограничивает ширину 1440", () => {
  render(<PageContainer as="main">x</PageContainer>);
  expect(screen.getByRole("main").className).toContain("max-w-[1440px]");
});

test("инициалы", () => {
  expect(initials("ivan.petrov@mail.ru")).toBe("IP");
  expect(initials("")).toBe("?");
});

test("счётчик приглашений: у нового кандидата без приглашений бейджа нет, свои отклики не считаются", async () => {
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

test("вкладки раздела: «Приглашения» кандидата показывают интересы, приглашения и отклики", async () => {
  const { SectionTabs } = await import("./SectionTabs");
  render(
    <MemoryRouter initialEntries={["/me/interests"]}>
      <SectionTabs nav={NAV.candidate} />
    </MemoryRouter>,
  );
  const tabs = screen.getByRole("navigation", { name: "Вкладки раздела" });
  expect(within(tabs).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["/me/interests", "/me/offers", "/me/responses"]);
  expect(within(tabs).getByRole("link", { name: "Интересы" })).toHaveAttribute("aria-current", "page");
});

test("вкладок нет у раздела без вкладок", async () => {
  const { SectionTabs } = await import("./SectionTabs");
  render(
    <MemoryRouter initialEntries={["/me"]}>
      <SectionTabs nav={NAV.candidate} />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("navigation", { name: "Вкладки раздела" })).toBeNull();
});
