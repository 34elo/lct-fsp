import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "../lib/cn";

export const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none aria-busy:pointer-events-none",
  {
    variants: {
      variant: {
        default: "bg-brand text-on-brand hover:bg-brand-deep",
        // Старое имя, оставлено для совместимости.
        primary: "bg-brand text-on-brand hover:bg-brand-deep",
        outline: "border border-brand-fg text-brand-fg hover:bg-tint-50",
        ghost: "text-ink hover:bg-tint-50",
        destructive: "bg-error text-white hover:opacity-90",
        link: "h-auto px-0 text-brand-fg underline-offset-4 hover:underline",
      },
      // Цель касания не меньше 44 px на телефоне (h-11), на широком экране sm компактнее.
      size: { md: "h-11 px-4", lg: "h-12 px-5", sm: "h-11 px-3 text-sm sm:h-9", icon: "size-11" },
    },
    defaultVariants: { variant: "default", size: "md" },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & { loading?: boolean };

export function Button({ className, variant, size, type = "button", loading, disabled, children, ...p }: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...p}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}
