import { buttonVariants, cn } from "@fsp/ui";
import type { HTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

import { T } from "./text";

/* Общие кирпичи лендинга: контейнер макета (1280 px, поле 24 / 16), заголовки блоков, кнопки призыва.
   Перелом раскладки — 860 px, как в макете (`min-[861px]:`). */

export function Wrap({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("relative mx-auto w-full max-w-[1280px] px-4 min-[861px]:px-6", className)} {...p} />;
}

export const sectionY = "py-14 min-[861px]:py-24";

/** A9: карточка поднимается на 4 px с тенью за 180 мс. */
export const hoverLift =
  "shadow-[0_24px_56px_rgba(27,28,33,.14)] dark:shadow-[0_24px_56px_rgba(0,0,0,.45)] transition-[transform,box-shadow,border-color] duration-[180ms] ease-out hover:-translate-y-1 hover:border-tint-200 hover:shadow-[0_16px_36px_rgba(27,28,33,.12)] dark:hover:shadow-[0_16px_36px_rgba(0,0,0,.4)]";

export function SecLabel({ className, ...p }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("font-mono text-[13px] leading-[1.4] font-medium tracking-[.02em] text-brand-fg", className)} {...p} />;
}

export function SecTitle({ className, ...p }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2
      className={cn("m-0 font-mono text-[26px] leading-[1.2] font-semibold tracking-[-0.01em] min-[861px]:text-[34px]", className)}
      {...p}
    />
  );
}

/** Заголовок блока: метка и название. */
export function SecHead({ label, title, children }: { label: string; title: ReactNode; children?: ReactNode }) {
  return (
    <>
      <SecLabel>{label}</SecLabel>
      <SecTitle className="mt-1.5">{title}</SecTitle>
      {children}
    </>
  );
}

const cta = "group h-[52px] gap-2 rounded-lg px-[26px] text-16 whitespace-nowrap hover:-translate-y-px active:translate-y-0 transition-[transform,box-shadow,background-color,border-color] duration-150 ease-out w-full min-[861px]:w-auto";

/** T1 и T2: две кнопки призыва. `onBrand` — на фоне цвета бренда (финальный блок). */
export function CtaPair({ onBrand, className }: { onBrand?: boolean; className?: string }) {
  return (
    <div className={cn("flex flex-col flex-wrap gap-3 min-[861px]:flex-row", onBrand && "justify-center", className)}>
      <Link
        to="/register"
        state={{ role: "candidate" }}
        className={cn(
          buttonVariants({ variant: "default" }),
          cta,
          "hover:bg-brand hover:shadow-[0_8px_20px_rgba(64,47,255,.28)]",
          onBrand && "bg-white text-brand hover:bg-white hover:shadow-[0_8px_20px_rgba(0,0,0,.2)]",
        )}
      >
        {T.ctaCandidate}
        <span aria-hidden="true" className="transition-transform duration-150 ease-out group-hover:translate-x-[3px]">
          →
        </span>
      </Link>
      <Link
        to="/register"
        state={{ role: "employer" }}
        className={cn(
          buttonVariants({ variant: "outline" }),
          cta,
          "dark:hover:bg-tint-100",
          onBrand && "border-white text-white hover:bg-white/15 dark:hover:bg-white/15",
        )}
      >
        {T.ctaEmployer}
      </Link>
    </div>
  );
}
