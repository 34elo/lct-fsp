import type { HTMLAttributes } from "react";

import { cn } from "./cn";

/** Область с принудительной темой: `<ThemeScope dark>` — тёмная (экран B, G1, hero), `light` — светлая внутри тёмной (класс `.light`, как `.dark .lt` в макетах v2). */
export function ThemeScope({
  dark,
  light,
  className,
  ...p
}: HTMLAttributes<HTMLDivElement> & { dark?: boolean; light?: boolean }) {
  const forced = dark ? "dark" : light ? "light" : "";
  return (
    <div
      data-theme-scope={forced || undefined}
      className={cn(forced, forced && "bg-page text-ink", className)}
      style={forced ? { colorScheme: forced } : undefined}
      {...p}
    />
  );
}
