import type { ReactNode } from "react";

import { cn } from "@fsp/ui";

/** Контейнер страницы: максимум 1440, поля 40 / 24 / 16 (E19-5). */
export function PageContainer({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "main";
}) {
  return <Tag className={cn("mx-auto w-full max-w-[1440px] px-4 md:px-6 lg:px-10", className)}>{children}</Tag>;
}
