import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/shared/lib/cn";

const button = cva(
  "inline-flex items-center justify-center rounded-lg font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary: "bg-brand text-on-brand hover:bg-brand-deep",
        outline: "border border-brand-fg text-brand-fg hover:bg-tint-50",
        ghost: "text-ink hover:bg-tint-50",
      },
      size: { md: "h-11 px-4", lg: "h-12 px-5", sm: "h-9 px-3 text-sm" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export function Button({
  className,
  variant,
  size,
  type = "button",
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof button>) {
  return <button type={type} className={cn(button({ variant, size }), className)} {...p} />;
}
