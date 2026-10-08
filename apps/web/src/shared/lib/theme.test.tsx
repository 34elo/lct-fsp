import { act, render, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";

import { titleFor } from "@/app/DocumentTitle";
import { ThemeProvider, useTheme } from "./theme";

function stubMedia(dark: boolean) {
  const listeners: Array<() => void> = [];
  const mq = { matches: dark, addEventListener: (_: string, f: () => void) => listeners.push(f), removeEventListener: () => {} };
  vi.stubGlobal("matchMedia", () => mq);
  return {
    flip(v: boolean) {
      mq.matches = v;
      listeners.forEach((f) => f());
    },
  };
}
const wrap = ({ children }: { children: ReactNode }) => <ThemeProvider>{children}</ThemeProvider>;

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});
afterEach(() => vi.unstubAllGlobals());

test("первый вход: тема системная (тёмная)", () => {
  stubMedia(true);
  const { result } = renderHook(() => useTheme(), { wrapper: wrap });
  expect(result.current.mode).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
});

test("первый вход: светлая система — светлая тема, смена системной темы подхватывается", () => {
  const m = stubMedia(false);
  const { result } = renderHook(() => useTheme(), { wrapper: wrap });
  expect(result.current.mode).toBe("light");
  act(() => m.flip(true));
  expect(result.current.mode).toBe("dark");
});

test("выбор пользователя сохраняется и сильнее системной темы; режима «система» нет", () => {
  const m = stubMedia(true);
  const { result } = renderHook(() => useTheme(), { wrapper: wrap });
  act(() => result.current.setMode("light"));
  expect(localStorage.getItem("fsp-theme")).toBe("light");
  act(() => m.flip(true));
  expect(result.current.mode).toBe("light");
  expect(document.documentElement.classList.contains("dark")).toBe(false);
});

test("устаревшее значение «system» в хранилище игнорируется", () => {
  stubMedia(true);
  localStorage.setItem("fsp-theme", "system");
  const { result } = renderHook(() => useTheme(), { wrapper: wrap });
  expect(result.current.mode).toBe("dark");
});

test("заголовок вкладки по экрану", () => {
  render(null);
  expect(titleFor("/me/settings")).toBe("Настройки · ФСП Карьера");
  expect(titleFor("/jobs/42")).toBe("Вакансия · ФСП Карьера");
  expect(titleFor("/")).toBe("ФСП Карьера");
  expect(titleFor("/nope")).toBe("ФСП Карьера");
});
