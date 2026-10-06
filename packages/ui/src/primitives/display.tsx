import { cva, type VariantProps } from "class-variance-authority";
import { AlertTriangle, Inbox, SearchX } from "lucide-react";
import { Progress as RProgress, Separator as RSeparator } from "radix-ui";
import type { ComponentProps, HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "../lib/cn";
import { Button } from "./button";

/* ---------- Card ---------- */
export function Card({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-hairline bg-card shadow-xs", className)} {...p} />;
}
export function CardHeader({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-5 pb-0", className)} {...p} />;
}
export function CardTitle({ className, ...p }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-16 font-semibold", className)} {...p} />;
}
export function CardContent({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...p} />;
}

/* ---------- Badge ---------- */
const badge = cva("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 font-mono text-12", {
  variants: {
    variant: {
      default: "border-tint-200 bg-tint-50 text-brand-fg",
      muted: "border-hairline bg-card text-muted",
      success: "border-success/30 bg-success-bg text-success",
      warning: "border-warning-border bg-warning-bg text-warning-fg",
      error: "border-error/30 bg-error-bg text-error",
      dashed: "border-dashed border-tint-200 text-muted",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...p }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ variant }), className)} {...p} />;
}

/* ---------- Skeleton ---------- */
/** Заглушка загрузки. Скринридеру сообщает «загрузка» через role=status. */
export function Skeleton({ className, ...p }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Загрузка"
      className={cn("animate-pulse rounded-lg bg-tint-100", className)}
      {...p}
    />
  );
}

/* ---------- Progress ---------- */
export function Progress({ value, className, ...p }: ComponentProps<typeof RProgress.Root>) {
  return (
    <RProgress.Root value={value} className={cn("relative h-2 w-full overflow-hidden rounded-full bg-tint-100", className)} {...p}>
      <RProgress.Indicator
        className="h-full rounded-full bg-brand transition-transform"
        style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
      />
    </RProgress.Root>
  );
}

/* ---------- Separator ---------- */
export function Separator({ className, orientation = "horizontal", decorative = true, ...p }: ComponentProps<typeof RSeparator.Root>) {
  return (
    <RSeparator.Root
      orientation={orientation}
      decorative={decorative}
      className={cn("shrink-0 bg-hairline", orientation === "horizontal" ? "h-px w-full" : "h-full w-px", className)}
      {...p}
    />
  );
}

/* ---------- Table ---------- */
export function Table({ className, ...p }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto">
      <table className={cn("w-full border-collapse text-14", className)} {...p} />
    </div>
  );
}
export function TableHeader(p: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead {...p} />;
}
export function TableBody(p: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody {...p} />;
}
export function TableRow({ className, ...p }: HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-hairline hover:bg-tint-50", className)} {...p} />;
}
export function TableHead({ className, ...p }: ThHTMLAttributes<HTMLTableCellElement>) {
  return <th scope="col" className={cn("lbl px-3 py-2 text-left text-muted", className)} {...p} />;
}
export function TableCell({ className, ...p }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-3", className)} {...p} />;
}

/* ---------- Состояния экрана: пусто, ошибка, 404 ---------- */
type StateProps = { title: string; description?: ReactNode; action?: ReactNode; className?: string };

/** Пустое состояние: пунктирная рамка, подсказка, что делать дальше. */
export function EmptyState({ title, description, action, className, icon }: StateProps & { icon?: ReactNode }) {
  return (
    <div className={cn("flex flex-col items-center gap-2 rounded-xl border border-dashed border-tint-200 px-5 py-10 text-center", className)}>
      <span className="text-muted" aria-hidden>
        {icon ?? <Inbox className="size-8" />}
      </span>
      <p className="text-16 font-semibold">{title}</p>
      {description && <p className="max-w-sm text-14 text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Ошибка загрузки: role=alert, кнопка «Повторить», если передан `onRetry`. */
export function ErrorState({
  title = "Не загрузилось",
  description,
  onRetry,
  action,
  className,
}: Partial<StateProps> & { onRetry?: () => void }) {
  return (
    <div role="alert" className={cn("flex flex-col items-center gap-2 rounded-xl border border-error/30 bg-error-bg px-5 py-10 text-center", className)}>
      <AlertTriangle className="size-8 text-error" aria-hidden />
      <p className="text-16 font-semibold text-error">{title}</p>
      {description && <p className="max-w-sm text-14 text-ink">{description}</p>}
      {(onRetry || action) && (
        <div className="mt-2 flex gap-2">
          {onRetry && (
            <Button variant="destructive" onClick={onRetry}>
              Повторить
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}

/** Страница 404. Ссылку «на главную» передаёт приложение (`action`), пакет от роутера не зависит. */
export function NotFound({ title = "Страница не найдена", description = "Возможно, ссылка устарела или адрес введён с ошибкой.", action, className }: Partial<StateProps>) {
  return (
    <div className={cn("mx-auto flex max-w-md flex-col items-center gap-3 px-4 py-16 text-center", className)}>
      <SearchX className="size-10 text-muted" aria-hidden />
      <p className="font-mono text-48 font-bold text-brand-fg">404</p>
      <h1 className="text-20 font-semibold">{title}</h1>
      <p className="text-14 text-muted">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
