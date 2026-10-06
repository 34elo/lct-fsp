import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { Providers, makeQueryClient } from "@/app/Providers";

import Landing from "./Landing";

describe("Landing", () => {
  it("показывает hero, шаги и ссылки на регистрацию без счётчиков", () => {
    render(
      <Providers client={makeQueryClient()}><MemoryRouter>
        <Landing />
      </MemoryRouter></Providers>,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Не резюме, а доказательства" })).toBeInTheDocument();
    expect(screen.getByText("Соберите профиль", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Я ищу работу" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: "Я ищу людей" })).toHaveAttribute("href", "/register");
    expect(screen.queryByText(/профилей/)).toBeNull();
  });
});
