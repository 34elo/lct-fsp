import { Info } from "lucide-react";
import { Popover as RPopover, Tabs as RTabs } from "radix-ui";
import { useEffect, useId, useLayoutEffect, useRef, useState, type ComponentProps, type PointerEvent, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "../lib/cn";
import { SegmentedControl } from "../primitives/overlay";

/* ---------- InfoTip ---------- */

/**
 * Значок ⓘ рядом с термином → карточка пояснения. Мышь — по наведению, касание и клавиатура — по нажатию.
 * Текст 1–2 предложения (словарь — E39-5).
 */
export function InfoTip({
  children,
  title,
  label = "Пояснение",
  side = "top",
  className,
  "data-testid": testId,
}: {
  children: ReactNode;
  title?: ReactNode;
  /** Подпись кнопки для скринридера: «Что такое доверие». */
  label?: string;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
  "data-testid"?: string;
}) {
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const hoverOpen = useRef(false);
  const cancel = () => clearTimeout(timer.current);
  const enter = (e: PointerEvent) => {
    if (e.pointerType !== "mouse") return;
    cancel();
    hoverOpen.current = true;
    setOpen(true);
  };
  const leave = (e: PointerEvent) => {
    if (e.pointerType !== "mouse" || !hoverOpen.current) return;
    cancel();
    timer.current = setTimeout(() => {
      hoverOpen.current = false;
      setOpen(false);
    }, 150);
  };
  useEffect(() => cancel, []);
  return (
    <RPopover.Root
      open={open}
      onOpenChange={(o) => {
        hoverOpen.current = false;
        setOpen(o);
      }}
    >
      <RPopover.Trigger asChild>
        <button
          type="button"
          aria-label={label}
          data-testid={testId}
          onPointerEnter={enter}
          onPointerLeave={leave}
          onClick={(e) => {
            // Клик после наведения не должен закрыть только что открытую карточку.
            if (hoverOpen.current) {
              e.preventDefault();
              hoverOpen.current = false;
            }
          }}
          className={cn(
            "relative inline-flex size-5 shrink-0 items-center justify-center rounded-full align-middle text-muted hover:text-brand-fg focus-visible:text-brand-fg data-[state=open]:text-brand-fg",
            // Цель касания 44 px без сдвига вёрстки.
            "after:absolute after:-inset-3 after:content-['']",
            className,
          )}
        >
          <Info className="size-4" aria-hidden />
        </button>
      </RPopover.Trigger>
      <RPopover.Portal>
        <RPopover.Content
          side={side}
          sideOffset={6}
          collisionPadding={16}
          onPointerEnter={enter}
          onPointerLeave={leave}
          className="z-50 max-w-[min(18rem,calc(100vw-32px))] rounded-lg border border-hairline bg-card p-3 text-13 leading-snug text-ink shadow-card"
        >
          {title && <p className="mb-1 font-semibold">{title}</p>}
          <div className="text-muted">{children}</div>
          <RPopover.Arrow className="fill-card" width={12} height={6} />
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  );
}

/** Термин с ⓘ: «Доверие ⓘ». */
export function Term({ children, tip, title, className }: { children: ReactNode; tip: ReactNode; title?: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {children}
      <InfoTip title={title} label={typeof children === "string" ? `Что такое «${children}»` : undefined}>
        {tip}
      </InfoTip>
    </span>
  );
}

/* ---------- Markdown ---------- */

/** Убираем служебный `node` из пропсов react-markdown, чтобы он не попал в DOM. */
function rest<T extends { node?: unknown }>(p: T): Omit<T, "node"> {
  const c = { ...p };
  delete c.node;
  return c;
}

const md: Components = {
  h1: (p) => <h3 className="mt-4 mb-2 text-20 font-semibold first:mt-0" {...rest(p)} />,
  h2: (p) => <h4 className="mt-4 mb-2 text-16 font-semibold first:mt-0" {...rest(p)} />,
  h3: (p) => <h5 className="mt-3 mb-1 text-14 font-semibold first:mt-0" {...rest(p)} />,
  p: (p) => <p className="my-2 first:mt-0 last:mb-0" {...rest(p)} />,
  a: (p) => <a className="text-brand-fg underline underline-offset-2" target="_blank" rel="noopener noreferrer" {...rest(p)} />,
  ul: (p) => <ul className="my-2 list-disc pl-5" {...rest(p)} />,
  ol: (p) => <ol className="my-2 list-decimal pl-5" {...rest(p)} />,
  li: (p) => <li className="my-0.5" {...rest(p)} />,
  blockquote: (p) => <blockquote className="my-2 border-l-2 border-tint-200 pl-3 text-muted" {...rest(p)} />,
  hr: () => <hr className="my-3 border-hairline" />,
  pre: (p) => <pre className="my-2 overflow-x-auto rounded-lg bg-tint-50 p-3 font-mono text-13 leading-relaxed [&_code]:bg-transparent [&_code]:p-0" {...rest(p)} />,
  code: (p) => <code {...rest(p)} className={cn("rounded-xs bg-tint-50 px-1 py-0.5 font-mono text-[0.92em]", p.className)} />,
  table: (p) => (
    <div className="my-2 w-full overflow-x-auto rounded-lg border border-hairline">
      <table className="w-full border-collapse text-13" {...rest(p)} />
    </div>
  ),
  th: (p) => <th className="border-b border-hairline bg-tint-50 px-3 py-2 text-left font-semibold" {...rest(p)} />,
  td: (p) => <td className="border-b border-hairline px-3 py-2 align-top [tr:last-child_&]:border-b-0" {...rest(p)} />,
  img: ({ alt }) => <span className="text-muted">[{alt || "изображение"}]</span>,
};

/**
 * Просмотр Markdown (GFM: таблицы, списки задач, зачёркивание). Сырой HTML не исполняется,
 * картинки не грузятся (только подпись), ссылки — в новой вкладке.
 */
export function Markdown({ children, className, "data-testid": testId }: { children: string; className?: string; "data-testid"?: string }) {
  return (
    <div className={cn("min-w-0 text-14 leading-relaxed break-words text-ink", className)} data-testid={testId}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={md} skipHtml>
        {children}
      </ReactMarkdown>
    </div>
  );
}

/** Правка Markdown с просмотром: «Текст» / «Просмотр». */
export function MarkdownEditor({
  value,
  onChange,
  placeholder,
  rows = 8,
  maxLength,
  id,
  disabled,
  className,
  "aria-label": ariaLabel,
  "data-testid": testId,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  maxLength?: number;
  id?: string;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
  "data-testid"?: string;
}) {
  const [mode, setMode] = useState<"edit" | "view">("edit");
  const autoId = useId();
  const tid = id ?? autoId;
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SegmentedControl
          label="Режим редактора"
          value={mode}
          onValueChange={(v) => setMode(v as "edit" | "view")}
          options={[
            { value: "edit", label: "Текст" },
            { value: "view", label: "Просмотр" },
          ]}
        />
        <span className="font-mono text-12 text-muted">
          Markdown: **жирный**, списки, таблицы{maxLength ? ` · ${value.length}/${maxLength}` : ""}
        </span>
      </div>
      {mode === "edit" ? (
        <textarea
          id={tid}
          rows={rows}
          value={value}
          maxLength={maxLength}
          placeholder={placeholder}
          disabled={disabled}
          aria-label={ariaLabel}
          data-testid={testId}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded-lg border border-hairline bg-card px-3 py-2 font-mono text-13 leading-relaxed text-ink placeholder:text-muted hover:border-brand-mid focus-visible:border-brand focus-visible:outline-2 focus-visible:outline-brand focus-visible:-outline-offset-1 disabled:bg-tint-50"
        />
      ) : (
        <div className="min-h-24 rounded-lg border border-hairline bg-card px-3 py-2" data-testid={testId ? `${testId}-preview` : undefined}>
          {value.trim() ? <Markdown>{value}</Markdown> : <p className="text-14 text-muted">Пока пусто</p>}
        </div>
      )}
    </div>
  );
}

/* ---------- ScrollTabs ---------- */

/**
 * Список вкладок с горизонтальной прокруткой (без вертикальной): вкладки не переносятся, активная
 * докручивается в видимую область. Замена `TabsList` внутри `Tabs`.
 */
export function ScrollTabs({ className, children, ...p }: ComponentProps<typeof RTabs.List>) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const box = ref.current;
    if (!box) return;
    const sync = () => {
      const on = box.querySelector<HTMLElement>("[data-state=active]");
      if (!on) return;
      const l = on.offsetLeft;
      const r = l + on.offsetWidth;
      if (l < box.scrollLeft) box.scrollLeft = l - 16;
      else if (r > box.scrollLeft + box.clientWidth) box.scrollLeft = r - box.clientWidth + 16;
    };
    sync();
    const mo = typeof MutationObserver !== "undefined" ? new MutationObserver(sync) : null;
    mo?.observe(box, { subtree: true, attributes: true, attributeFilter: ["data-state"] });
    return () => mo?.disconnect();
  }, []);
  return (
    <RTabs.List
      ref={ref}
      className={cn(
        "relative flex flex-nowrap gap-1 overflow-x-auto overflow-y-hidden overscroll-x-contain border-b border-hairline [scrollbar-width:none] [&::-webkit-scrollbar]:hidden [&>*]:shrink-0 [&>*]:whitespace-nowrap",
        className,
      )}
      {...p}
    >
      {children}
    </RTabs.List>
  );
}

/* ---------- Avatar ---------- */

/** «Анна Смирнова» → «АС», «backend» → «B». */
export function initials(name: string | null | undefined): string {
  const w = (name ?? "").trim().split(/[\s._-]+/).filter(Boolean);
  if (!w.length) return "?";
  return (w.length > 1 ? w[0]![0]! + w[1]![0]! : w[0]![0]!).toLocaleUpperCase("ru");
}

/** Аватар: фото, а без него или при ошибке загрузки — инициалы на оттенке бренда. */
export function Avatar({ name, src, size = 36, className, alt }: { name?: string | null; src?: string | null; size?: number; className?: string; alt?: string }) {
  const [broken, setBroken] = useState(false);
  const showImg = src && !broken;
  return (
    <span
      className={cn("inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-tint-100 font-mono font-semibold text-brand-fg select-none", className)}
      style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.4)) }}
      role="img"
      aria-label={alt ?? name ?? "Аватар"}
    >
      {showImg ? <img src={src} alt="" className="size-full object-cover" onError={() => setBroken(true)} /> : <span aria-hidden>{initials(name)}</span>}
    </span>
  );
}
