import { X } from "lucide-react";
import { Dialog as RDialog, DropdownMenu as RMenu, Popover as RPopover, Tabs as RTabs, ToggleGroup as RToggle, Tooltip as RTooltip } from "radix-ui";
import type { ComponentProps, ReactNode } from "react";
import { Toaster as Sonner } from "sonner";

import { cn } from "../lib/cn";

/* ---------- Tabs ---------- */
export const Tabs = RTabs.Root;

export function TabsList({ className, ...p }: ComponentProps<typeof RTabs.List>) {
  return <RTabs.List className={cn("flex gap-1 overflow-x-auto border-b border-hairline", className)} {...p} />;
}

/** Вкладка; `count` — счётчик справа («Шорт-лист 3»). */
export function TabsTrigger({ className, children, count, ...p }: ComponentProps<typeof RTabs.Trigger> & { count?: number }) {
  return (
    <RTabs.Trigger
      className={cn(
        "-mb-px inline-flex min-h-11 items-center gap-2 border-b-2 border-transparent px-3 text-14 font-medium text-muted hover:text-ink data-[state=active]:border-brand data-[state=active]:text-ink disabled:opacity-50",
        className,
      )}
      {...p}
    >
      {children}
      {count !== undefined && <span className="rounded-full bg-tint-100 px-1.5 font-mono text-12 text-brand-fg">{count}</span>}
    </RTabs.Trigger>
  );
}

export const TabsContent = RTabs.Content;

/* ---------- SegmentedControl ---------- */
export type SegmentedOption = { value: string; label: ReactNode; disabled?: boolean };

/** Переключатель одного значения («уровень доверия» в A). */
export function SegmentedControl({
  value,
  onValueChange,
  options,
  label,
  className,
}: {
  value: string;
  onValueChange: (v: string) => void;
  options: SegmentedOption[];
  label: string;
  className?: string;
}) {
  return (
    <RToggle.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onValueChange(v)}
      aria-label={label}
      className={cn("inline-flex rounded-lg border border-hairline bg-card p-0.5", className)}
    >
      {options.map((o) => (
        <RToggle.Item
          key={o.value}
          value={o.value}
          disabled={o.disabled}
          className="inline-flex min-h-11 items-center rounded-md px-3 text-13 font-medium text-muted hover:text-ink data-[state=on]:bg-brand data-[state=on]:text-on-brand disabled:opacity-50 sm:min-h-8"
        >
          {o.label}
        </RToggle.Item>
      ))}
    </RToggle.Root>
  );
}

/* ---------- Dialog / Sheet ---------- */
export const Dialog = RDialog.Root;
export const DialogTrigger = RDialog.Trigger;
export const DialogClose = RDialog.Close;

const overlay = "fixed inset-0 z-50 bg-ink/40";
const closeBtn =
  "absolute right-2 top-2 inline-flex size-11 items-center justify-center rounded-md text-muted hover:bg-tint-50 hover:text-ink";

export function DialogContent({ className, children, ...p }: ComponentProps<typeof RDialog.Content>) {
  return (
    <RDialog.Portal>
      <RDialog.Overlay className={overlay} />
      <RDialog.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-hairline bg-card p-5 shadow-sheet",
          className,
        )}
        {...p}
      >
        {children}
        <RDialog.Close className={closeBtn} aria-label="Закрыть">
          <X className="size-4" aria-hidden />
        </RDialog.Close>
      </RDialog.Content>
    </RDialog.Portal>
  );
}

export function DialogTitle({ className, ...p }: ComponentProps<typeof RDialog.Title>) {
  return <RDialog.Title className={cn("pr-10 text-20 font-semibold", className)} {...p} />;
}

export function DialogDescription({ className, ...p }: ComponentProps<typeof RDialog.Description>) {
  return <RDialog.Description className={cn("mt-1 text-14 text-muted", className)} {...p} />;
}

const sheetSide = {
  bottom: "inset-x-0 bottom-0 max-h-[85vh] rounded-t-xl border-t",
  right: "inset-y-0 right-0 w-[min(24rem,100%)] border-l",
} as const;

/** Sheet: нижний лист (на телефоне) или правая панель. */
export function SheetContent({
  side = "bottom",
  className,
  children,
  ...p
}: ComponentProps<typeof RDialog.Content> & { side?: keyof typeof sheetSide }) {
  return (
    <RDialog.Portal>
      <RDialog.Overlay className={overlay} />
      <RDialog.Content
        data-side={side}
        className={cn("fixed z-50 overflow-y-auto border-hairline bg-card p-5 shadow-sheet", sheetSide[side], className)}
        {...p}
      >
        {children}
        <RDialog.Close className={closeBtn} aria-label="Закрыть">
          <X className="size-4" aria-hidden />
        </RDialog.Close>
      </RDialog.Content>
    </RDialog.Portal>
  );
}

export const Sheet = RDialog.Root;
export const SheetTrigger = RDialog.Trigger;
export const SheetTitle = DialogTitle;
export const SheetDescription = DialogDescription;

/* ---------- Popover / Tooltip ---------- */
export const Popover = RPopover.Root;
export const PopoverTrigger = RPopover.Trigger;

export function PopoverContent({ className, sideOffset = 6, ...p }: ComponentProps<typeof RPopover.Content>) {
  return (
    <RPopover.Portal>
      <RPopover.Content
        sideOffset={sideOffset}
        className={cn("z-50 w-72 rounded-lg border border-hairline bg-card p-3 text-14 shadow-card", className)}
        {...p}
      />
    </RPopover.Portal>
  );
}

export const TooltipProvider = RTooltip.Provider;
export const Tooltip = RTooltip.Root;
export const TooltipTrigger = RTooltip.Trigger;

export function TooltipContent({ className, sideOffset = 6, ...p }: ComponentProps<typeof RTooltip.Content>) {
  return (
    <RTooltip.Portal>
      <RTooltip.Content
        sideOffset={sideOffset}
        className={cn("z-50 rounded-md bg-ink px-2 py-1 text-12 text-page", className)}
        {...p}
      />
    </RTooltip.Portal>
  );
}

/* ---------- DropdownMenu ---------- */
export const DropdownMenu = RMenu.Root;
export const DropdownMenuTrigger = RMenu.Trigger;

export function DropdownMenuContent({ className, sideOffset = 6, ...p }: ComponentProps<typeof RMenu.Content>) {
  return (
    <RMenu.Portal>
      <RMenu.Content
        sideOffset={sideOffset}
        className={cn("z-50 min-w-44 rounded-lg border border-hairline bg-card p-1 shadow-card", className)}
        {...p}
      />
    </RMenu.Portal>
  );
}

export function DropdownMenuItem({ className, ...p }: ComponentProps<typeof RMenu.Item>) {
  return (
    <RMenu.Item
      className={cn(
        "flex min-h-11 cursor-pointer items-center gap-2 rounded-md px-3 text-14 outline-none data-[highlighted]:bg-tint-50 data-[disabled]:opacity-50 sm:min-h-9",
        className,
      )}
      {...p}
    />
  );
}

export function DropdownMenuSeparator({ className, ...p }: ComponentProps<typeof RMenu.Separator>) {
  return <RMenu.Separator className={cn("my-1 h-px bg-hairline", className)} {...p} />;
}

/* ---------- Toast (sonner) ---------- */
export { toast } from "sonner";

/** Один раз на приложение. Цвета — из токенов. */
export function Toaster(p: ComponentProps<typeof Sonner>) {
  return (
    <Sonner
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border !border-hairline !bg-card !text-ink !shadow-card !font-sans !text-14",
          success: "!bg-success-bg !text-success",
          error: "!bg-error-bg !text-error",
        },
      }}
      {...p}
    />
  );
}
