import { fireEvent, screen } from "@testing-library/react";

/** Тесты: выбрать вариант в `Select`/`Combobox` из `@fsp/ui` по подписи (список рендерится в портале). */
export function pickOption(control: HTMLElement, label: string | RegExp) {
  if (control.getAttribute("aria-expanded") !== "true") fireEvent.click(control);
  fireEvent.click(screen.getByRole("option", { name: label }));
}
