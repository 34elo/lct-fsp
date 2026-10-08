import type { ReactNode } from "react";

import { cn } from "@fsp/ui";

import { PAGE, type PageWidth } from "@/shared/lib/page";

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

/** Страница с одной из трёх ширин сетки (E39-4): `narrow` — формы, `normal` — списки, `wide` — таблицы. */
export function Page({
  width = "normal",
  as: Tag = "div",
  className,
  children,
  ...rest
}: {
  width?: PageWidth;
  as?: "div" | "main" | "section";
  className?: string;
  children: ReactNode;
  "data-testid"?: string;
}) {
  return (
    <Tag className={cn(PAGE[width], className)} {...rest}>
      {children}
    </Tag>
  );
}
