import { Check, Loader2 } from "lucide-react";
import { Checkbox as RCheckbox, Label as RLabel, RadioGroup as RRadio, Slider as RSlider, Switch as RSwitch } from "radix-ui";
import { createContext, useContext, useId, type ComponentProps, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";

import { cn } from "../lib/cn";

const control =
  "w-full rounded-lg border border-hairline bg-card px-3 text-14 text-ink placeholder:text-muted hover:border-brand-mid focus-visible:border-brand focus-visible:outline-2 focus-visible:outline-brand focus-visible:-outline-offset-1 disabled:cursor-not-allowed disabled:bg-tint-50 disabled:text-muted aria-[invalid=true]:border-error aria-[invalid=true]:text-error";

export function Label({ className, ...p }: ComponentProps<typeof RLabel.Root>) {
  return <RLabel.Root className={cn("text-13 font-medium text-ink", className)} {...p} />;
}

export function Input({ className, loading, ...p }: InputHTMLAttributes<HTMLInputElement> & { loading?: boolean }) {
  const input = <input className={cn(control, "h-11", loading && "pr-9", className)} aria-busy={loading || undefined} {...p} />;
  if (!loading) return input;
  return (
    <span className="relative block">
      {input}
      <Loader2 className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-brand-fg" aria-hidden />
    </span>
  );
}

export function Textarea({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(control, "min-h-24 py-2", className)} {...p} />;
}

const FieldCtx = createContext<{ id: string; error?: string; hintId: string } | null>(null);

/** Поле: подпись, элемент, подсказка и ошибка. Элемент берёт id и aria-связи через `useFieldProps` или `FieldInput`. */
export function Field({ label, hint, error, children, className }: { label: ReactNode; hint?: ReactNode; error?: string; children: ReactNode; className?: string }) {
  const id = useId();
  const hintId = `${id}-msg`;
  return (
    <FieldCtx.Provider value={{ id, error, hintId }}>
      <div className={cn("flex flex-col gap-1.5", className)}>
        <Label htmlFor={id}>{label}</Label>
        {children}
        {error ? (
          <FormMessage id={hintId} error>
            {error}
          </FormMessage>
        ) : hint ? (
          <FormMessage id={hintId}>{hint}</FormMessage>
        ) : null}
      </div>
    </FieldCtx.Provider>
  );
}

export function useFieldProps() {
  const c = useContext(FieldCtx);
  return c ? { id: c.id, "aria-invalid": c.error ? true : undefined, "aria-describedby": c.hintId } : {};
}

export function FieldInput(p: InputHTMLAttributes<HTMLInputElement> & { loading?: boolean }) {
  return <Input {...useFieldProps()} {...p} />;
}

export function FormMessage({ error, className, ...p }: ComponentProps<"p"> & { error?: boolean }) {
  return <p role={error ? "alert" : undefined} className={cn("text-12", error ? "text-error" : "text-muted", className)} {...p} />;
}

export function Checkbox({ className, ...p }: ComponentProps<typeof RCheckbox.Root>) {
  return (
    <RCheckbox.Root
      className={cn("flex size-5 shrink-0 items-center justify-center rounded-sm border border-hairline bg-card hover:border-brand-mid data-[state=checked]:border-brand data-[state=checked]:bg-brand disabled:opacity-50", className)}
      {...p}
    >
      <RCheckbox.Indicator>
        <Check className="size-3.5 text-on-brand" aria-hidden />
      </RCheckbox.Indicator>
    </RCheckbox.Root>
  );
}

export function RadioGroup({ className, ...p }: ComponentProps<typeof RRadio.Root>) {
  return <RRadio.Root className={cn("grid gap-2", className)} {...p} />;
}

export function RadioGroupItem({ className, ...p }: ComponentProps<typeof RRadio.Item>) {
  return (
    <RRadio.Item
      className={cn("flex size-5 shrink-0 items-center justify-center rounded-full border border-hairline bg-card hover:border-brand-mid data-[state=checked]:border-brand disabled:opacity-50", className)}
      {...p}
    >
      <RRadio.Indicator className="size-2.5 rounded-full bg-brand" />
    </RRadio.Item>
  );
}

export function Switch({ className, ...p }: ComponentProps<typeof RSwitch.Root>) {
  return (
    <RSwitch.Root
      className={cn(
        // v2 `.sw`: 36×20, выкл — tint-200, вкл — brand; цель касания добирается полями строки настроек.
        "inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-tint-200 p-0.5 transition-colors data-[state=checked]:bg-brand disabled:opacity-50",
        className,
      )}
      {...p}
    >
      <RSwitch.Thumb className="block size-4 rounded-full bg-on-brand shadow-xs transition-transform data-[state=checked]:translate-x-4" />
    </RSwitch.Root>
  );
}

export function Slider({ className, ...p }: ComponentProps<typeof RSlider.Root>) {
  const count = (p.value ?? p.defaultValue ?? [0]).length;
  return (
    <RSlider.Root className={cn("relative flex h-11 w-full touch-none select-none items-center data-[disabled]:opacity-50", className)} {...p}>
      <RSlider.Track className="relative h-1.5 grow rounded-full bg-tint-100">
        <RSlider.Range className="absolute h-full rounded-full bg-brand" />
      </RSlider.Track>
      {Array.from({ length: count }, (_, i) => (
        <RSlider.Thumb key={i} aria-label={count > 1 ? (i === 0 ? "От" : "До") : "Значение"} className="block size-5 rounded-full border-2 border-brand bg-card shadow-xs" />
      ))}
    </RSlider.Root>
  );
}
