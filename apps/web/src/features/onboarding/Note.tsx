import { cn } from "@fsp/ui";
import type { ReactNode } from "react";

/** Сообщение об ошибке шага онбординга (role=alert, цвета из токенов). */
export function Note({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p role="alert" className={cn("rounded-lg bg-error-bg px-3 py-2 text-14 text-error", className)}>
      {children}
    </p>
  );
}
