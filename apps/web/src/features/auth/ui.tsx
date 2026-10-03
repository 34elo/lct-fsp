import type { ReactNode } from "react";

import { cn } from "@/shared/lib/cn";

export const fieldClass =
  "h-11 w-full rounded-lg border border-hairline bg-card px-3 text-ink placeholder:text-muted";

/** Карточка формы входа/регистрации: узкая колонка, на 375 px — во всю ширину. */
export function AuthCard({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <section className="mx-auto flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-hairline bg-card p-5 md:p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold">{title}</h1>
        {lead && <p className="text-sm text-muted">{lead}</p>}
      </header>
      {children}
    </section>
  );
}

export function ErrorNote({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p role="alert" className={cn("rounded-lg bg-error-bg px-3 py-2 text-sm text-error", className)}>
      {children}
    </p>
  );
}
