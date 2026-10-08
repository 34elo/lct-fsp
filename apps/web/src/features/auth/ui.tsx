import { Card, cn } from "@fsp/ui";
import type { ReactNode } from "react";


export const fieldClass =
  "h-11 w-full rounded-lg border border-hairline bg-card px-3 text-ink placeholder:text-muted";

/** Карточка формы входа/регистрации (M1/DS3): колонка 440 px по центру экрана, на 375 px — во всю ширину. */
export function AuthCard({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-[calc(100dvh-9rem)] items-center justify-center">
      <Card data-testid="auth-card" className="flex w-full max-w-[440px] flex-col gap-4 p-5 md:p-6">
        <header className="flex flex-col gap-1">
          <h1 className="text-24 font-bold">{title}</h1>
          {lead && <p className="text-14 text-muted">{lead}</p>}
        </header>
        {children}
      </Card>
    </div>
  );
}

export function ErrorNote({ children, className, ...rest }: { children: ReactNode; className?: string; "data-testid"?: string }) {
  return (
    <p role="alert" className={cn("rounded-lg bg-error-bg px-3 py-2 text-sm text-error", className)} {...rest}>
      {children}
    </p>
  );
}
