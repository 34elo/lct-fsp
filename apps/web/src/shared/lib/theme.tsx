import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/** Только светлая и тёмная. Пока выбора нет (первый вход), тема следует системной. */
export type ThemeMode = "light" | "dark";
const KEY = "fsp-theme";

function readStored(): ThemeMode | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null;
  }
}

function systemDark(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches;
}

export function applyTheme(mode: ThemeMode) {
  document.documentElement.classList.toggle("dark", mode === "dark");
}

const Ctx = createContext<{ mode: ThemeMode; setMode: (m: ThemeMode) => void } | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [chosen, setChosen] = useState<ThemeMode | null>(readStored);
  const [sys, setSys] = useState<ThemeMode>(() => (systemDark() ? "dark" : "light"));
  const mode = chosen ?? sys;

  useEffect(() => {
    applyTheme(mode);
  }, [mode]);

  useEffect(() => {
    if (chosen || typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const on = () => setSys(mq.matches ? "dark" : "light");
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [chosen]);

  const setMode = useCallback((m: ThemeMode) => {
    try {
      localStorage.setItem(KEY, m);
    } catch {
      /* хранилище недоступно: тема живёт до перезагрузки */
    }
    setChosen(m);
  }, []);

  const value = useMemo(() => ({ mode, setMode }), [mode, setMode]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useTheme() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTheme вне ThemeProvider");
  return v;
}
