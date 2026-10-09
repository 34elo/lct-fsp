import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Legal from "./Legal";
import Landing from "./Landing";
import { Providers, makeQueryClient } from "@/app/Providers";
import { ROUTES } from "@/app/routes";

const at = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/terms" element={<Legal />} />
        <Route path="/privacy" element={<Legal />} />
      </Routes>
    </MemoryRouter>,
  );

test("«Условия» и «Приватность» — публичные страницы без входа", () => {
  expect(ROUTES.find((r) => r.path === "/terms")?.section).toBe("public");
  expect(ROUTES.find((r) => r.path === "/privacy")?.section).toBe("public");
  at("/terms");
  expect(screen.getByRole("heading", { name: "Условия" })).toBeInTheDocument();
});

test("страница приватности показывает свой текст", () => {
  at("/privacy");
  expect(screen.getByRole("heading", { name: "Приватность" })).toBeInTheDocument();
});

test("подвал лендинга ведёт на /terms и /privacy, а не на согласия", () => {
  render(
    <Providers client={makeQueryClient()}>
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    </Providers>,
  );
  expect(screen.getByRole("link", { name: "Документы" })).toHaveAttribute("href", "/terms");
  expect(screen.getByRole("link", { name: "Политика ПДн" })).toHaveAttribute("href", "/privacy");
});
