import { Check, ChevronDown, Loader2, X } from "lucide-react";
import { Popover as RPopover } from "radix-ui";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "../lib/cn";
import { useFieldProps } from "../primitives/form";

/** Вариант списка. `isNew` — значение, которого нет в справочнике (создано пользователем). */
export interface ComboOption {
  value: string;
  label: string;
  hint?: string;
  disabled?: boolean;
  isNew?: boolean;
}

/** Асинхронный источник вариантов: строка поиска → варианты. `signal` отменяет устаревший запрос. */
export type OptionSource = (query: string, signal: AbortSignal) => Promise<ComboOption[]>;

interface ComboBase {
  /** Статичный список. Фильтруется по строке поиска на клиенте. */
  options?: ComboOption[];
  /** Асинхронный источник (подсказки с сервера). Заменяет `options` в выпадающем списке. */
  loadOptions?: OptionSource;
  /** Поле поиска внутри контрола. По умолчанию — у `Combobox` да, у `Select` нет. */
  searchable?: boolean;
  /** Разрешить своё значение: последним пунктом «Добавить «…»». */
  creatable?: boolean;
  createLabel?: (query: string) => string;
  /** Подписи выбранных значений, которых может не быть в `options` (асинхронный источник). */
  selectedOptions?: ComboOption[];
  /** Своя отрисовка чипса выбранного значения (мультивыбор). */
  renderChip?: (o: ComboOption) => ReactNode;
  placeholder?: string;
  emptyText?: string;
  disabled?: boolean;
  id?: string;
  className?: string;
  "aria-label"?: string;
  "aria-invalid"?: boolean;
  "data-testid"?: string;
  /** Сколько вариантов показывать (длинные справочники). */
  limit?: number;
  /** Задержка перед запросом к `loadOptions`, мс. */
  debounceMs?: number;
}

export type ComboboxSingleProps = ComboBase & {
  multiple?: false;
  value: string | null;
  onChange: (value: string | null, option: ComboOption | null) => void;
  /** Крестик «очистить». */
  clearable?: boolean;
};

export type ComboboxMultiProps = ComboBase & {
  multiple: true;
  value: string[];
  onChange: (value: string[], options: ComboOption[]) => void;
  max?: number;
};

export type ComboboxProps = ComboboxSingleProps | ComboboxMultiProps;

const shell =
  "flex w-full min-h-11 flex-wrap items-center gap-1.5 rounded-lg border border-hairline bg-card px-3 py-1.5 text-14 text-ink hover:border-brand-mid focus-within:border-brand focus-within:outline-2 focus-within:outline-brand focus-within:-outline-offset-1 aria-disabled:cursor-not-allowed aria-disabled:bg-tint-50 aria-disabled:text-muted data-[invalid=true]:border-error";

const norm = (s: string) => s.trim().toLocaleLowerCase("ru");

/** Чипс выбранного значения: подпись, метка «новый», крестик. */
export function ValueChip({ option, onRemove, disabled }: { option: ComboOption; onRemove?: () => void; disabled?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-sm border px-2 py-0.5 font-mono text-12 font-medium",
        option.isNew ? "border-dashed border-tint-200 bg-card text-muted" : "border-tint-200 bg-tint-50 text-chip-fg",
      )}
      data-new={option.isNew || undefined}
    >
      <span className="truncate">{option.label}</span>
      {option.isNew && <span className="rounded-xs bg-tint-100 px-1 text-11 text-brand-fg">новый</span>}
      {onRemove && !disabled && (
        <button
          type="button"
          tabIndex={-1}
          data-remove
          aria-label={`Убрать ${option.label}`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={onRemove}
          className="-mr-1 inline-flex size-5 items-center justify-center rounded-xs text-muted hover:bg-tint-100 hover:text-ink"
        >
          <X className="size-3" aria-hidden />
        </button>
      )}
    </span>
  );
}

/**
 * Выбор из списка со своим выпадающим списком: поиск, клавиатура (↑ ↓ Home End Enter Esc, Backspace убирает
 * последний чипс), мультивыбор чипсами, асинхронные подсказки, своё значение. ARIA — шаблон combobox + listbox.
 */
export function Combobox(props: ComboboxProps) {
  const {
    options = [],
    loadOptions,
    creatable,
    createLabel = (q) => `Добавить «${q}»`,
    selectedOptions,
    renderChip,
    placeholder = "Выберите",
    emptyText = "Ничего не найдено",
    disabled,
    className,
    limit = 50,
    debounceMs = 200,
  } = props;
  const multiple = props.multiple === true;
  const searchable = props.searchable ?? true;
  const field = useFieldProps() as { id?: string; "aria-invalid"?: boolean; "aria-describedby"?: string };
  const autoId = useId();
  const id = props.id ?? field.id ?? autoId;
  const listId = `${id}-list`;
  const invalid = props["aria-invalid"] ?? field["aria-invalid"];

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);
  const [remote, setRemote] = useState<ComboOption[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<Map<string, ComboOption>>(() => new Map());
  const anchorRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement & HTMLButtonElement>(null);

  const values = useMemo(() => (multiple ? (props.value as string[]) : props.value == null ? [] : [props.value as string]), [multiple, props.value]);

  // Все известные подписи: выбранные, статичные, найденные, созданные.
  const known = useMemo(() => {
    const m = new Map<string, ComboOption>();
    for (const o of selectedOptions ?? []) m.set(o.value, o);
    for (const o of options) m.set(o.value, o);
    for (const o of remote ?? []) if (!m.has(o.value)) m.set(o.value, o);
    for (const [k, o] of picked) if (!m.has(k)) m.set(k, o);
    return m;
  }, [selectedOptions, options, remote, picked]);
  const optionOf = useCallback((v: string): ComboOption => known.get(v) ?? { value: v, label: v }, [known]);

  // Асинхронные подсказки: с задержкой, устаревший запрос отменяется.
  useEffect(() => {
    if (!open || !loadOptions) return;
    const ctl = new AbortController();
    const t = setTimeout(() => {
      setLoading(true);
      loadOptions(query.trim(), ctl.signal)
        .then((r) => {
          if (!ctl.signal.aborted) setRemote(r);
        })
        .catch(() => {
          if (!ctl.signal.aborted) setRemote([]);
        })
        .finally(() => {
          if (!ctl.signal.aborted) setLoading(false);
        });
    }, debounceMs);
    return () => {
      clearTimeout(t);
      ctl.abort();
    };
  }, [open, query, loadOptions, debounceMs]);

  const items = useMemo(() => {
    const q = norm(query);
    let list = loadOptions ? (remote ?? []) : options;
    if (!loadOptions && searchable && q) list = list.filter((o) => norm(o.label).includes(q) || norm(o.value).includes(q));
    list = list.slice(0, limit);
    const t = query.trim();
    if (creatable && t && !list.some((o) => norm(o.label) === q) && !values.some((v) => norm(optionOf(v).label) === q)) {
      list = [...list, { value: t, label: t, isNew: true, hint: createLabel(t) }];
    }
    return list;
  }, [query, loadOptions, remote, options, searchable, limit, creatable, createLabel, values, optionOf]);

  const firstEnabled = (from: number, dir: 1 | -1) => {
    for (let i = from; i >= 0 && i < items.length; i += dir) if (!items[i]?.disabled) return i;
    return -1;
  };

  useEffect(() => {
    if (!open || active < 0) return;
    document.getElementById(`${id}-opt-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open, id]);

  const openList = () => {
    if (disabled || open) return;
    setOpen(true);
    const sel = items.findIndex((o) => values.includes(o.value));
    setActive(sel >= 0 ? sel : firstEnabled(0, 1));
  };
  const close = () => {
    setOpen(false);
    setActive(-1);
    setQuery("");
  };

  const emitMulti = (next: string[]) => (props as ComboboxMultiProps).onChange(next, next.map(optionOf));

  const pick = (o: ComboOption) => {
    if (o.disabled) return;
    setPicked((m) => new Map(m).set(o.value, o));
    if (multiple) {
      const mp = props as ComboboxMultiProps;
      const has = values.includes(o.value);
      if (!has && mp.max !== undefined && values.length >= mp.max) return;
      const next = has ? values.filter((v) => v !== o.value) : [...values, o.value];
      mp.onChange(next, next.map((v) => (v === o.value ? o : optionOf(v))));
      setQuery("");
      inputRef.current?.focus();
    } else {
      (props as ComboboxSingleProps).onChange(o.value, o);
      close();
    }
  };

  const remove = (v: string) => emitMulti(values.filter((x) => x !== v));

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (disabled) return;
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openList();
        else
          setActive((a) => {
            const n = firstEnabled(a + 1, 1);
            return n === -1 ? a : n;
          });
        break;
      case "ArrowUp":
        e.preventDefault();
        if (!open) openList();
        else
          setActive((a) => {
            const n = a <= 0 ? -1 : firstEnabled(a - 1, -1);
            return n === -1 ? a : n;
          });
        break;
      case "Home":
        if (open && !searchable) {
          e.preventDefault();
          setActive(firstEnabled(0, 1));
        }
        break;
      case "End":
        if (open && !searchable) {
          e.preventDefault();
          setActive(firstEnabled(items.length - 1, -1));
        }
        break;
      case "Enter":
        if (open) {
          e.preventDefault();
          const o = items[active];
          if (o) pick(o);
        } else if (!searchable) {
          e.preventDefault();
          openList();
        }
        break;
      case " ":
        if (!searchable) {
          e.preventDefault();
          if (open) {
            const o = items[active];
            if (o) pick(o);
          } else openList();
        }
        break;
      case "Escape":
        if (open) {
          e.preventDefault();
          e.stopPropagation();
          close();
        }
        break;
      case "Tab":
        if (open) close();
        break;
      case "Backspace":
        if (multiple && searchable && !query && values.length) remove(values[values.length - 1]!);
        break;
    }
  };

  const single = !multiple ? (values[0] !== undefined ? optionOf(values[0]) : null) : null;
  const activeId = open && active >= 0 ? `${id}-opt-${active}` : undefined;
  const ariaCommon = {
    id,
    role: "combobox" as const,
    "aria-expanded": open,
    "aria-controls": listId,
    "aria-haspopup": "listbox" as const,
    "aria-activedescendant": activeId,
    "aria-label": props["aria-label"],
    "aria-invalid": invalid || undefined,
    "aria-describedby": field["aria-describedby"],
    "data-testid": props["data-testid"],
    disabled,
    onKeyDown,
  };

  const chips = multiple
    ? values.map((v) => {
        const o = optionOf(v);
        return <span key={v}>{renderChip ? renderChip(o) : <ValueChip option={o} onRemove={() => remove(v)} disabled={disabled} />}</span>;
      })
    : null;

  return (
    <RPopover.Root open={open} onOpenChange={(o) => (o ? openList() : close())}>
      <RPopover.Anchor asChild>
        <div
          ref={anchorRef}
          className={cn(shell, className)}
          aria-disabled={disabled || undefined}
          data-invalid={invalid || undefined}
          onMouseDown={(e) => {
            if (disabled || e.target === inputRef.current) return;
            if ((e.target as HTMLElement).closest("button[data-remove],button[data-clear]")) return;
            e.preventDefault();
            inputRef.current?.focus();
            if (open && !searchable) close();
            else openList();
          }}
        >
          {chips}
          {searchable ? (
            <input
              {...ariaCommon}
              ref={inputRef}
              type="text"
              autoComplete="off"
              aria-autocomplete="list"
              value={open ? query : multiple ? query : (single?.label ?? "")}
              placeholder={multiple && values.length ? "" : (single?.label ?? placeholder)}
              onChange={(e) => {
                setQuery(e.target.value);
                if (!open) setOpen(true);
                setActive(0);
              }}
              onClick={openList}
              onBlur={() => setTimeout(() => {
                if (!anchorRef.current?.contains(document.activeElement)) close();
              }, 0)}
              className="h-7 min-w-16 flex-1 bg-transparent outline-none placeholder:text-muted disabled:cursor-not-allowed"
            />
          ) : (
            <button
              {...ariaCommon}
              ref={inputRef}
              type="button"
              onClick={() => (open ? close() : openList())}
              onBlur={() => setTimeout(() => {
                if (!anchorRef.current?.contains(document.activeElement)) close();
              }, 0)}
              className={cn("h-7 min-w-0 flex-1 truncate text-left outline-none disabled:cursor-not-allowed", !single && !(multiple && values.length) && "text-muted")}
            >
              {single ? single.label : multiple && values.length ? "" : placeholder}
            </button>
          )}
          {loading ? (
            <Loader2 className="size-4 shrink-0 animate-spin text-brand-fg" aria-hidden />
          ) : !multiple && (props as ComboboxSingleProps).clearable && single && !disabled ? (
            <button
              type="button"
              data-clear
              tabIndex={-1}
              aria-label="Очистить"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => (props as ComboboxSingleProps).onChange(null, null)}
              className="inline-flex size-6 shrink-0 items-center justify-center rounded-xs text-muted hover:text-ink"
            >
              <X className="size-3.5" aria-hidden />
            </button>
          ) : (
            <ChevronDown className={cn("size-4 shrink-0 text-muted transition-transform", open && "rotate-180")} aria-hidden />
          )}
        </div>
      </RPopover.Anchor>
      <RPopover.Portal>
        <RPopover.Content
          align="start"
          sideOffset={4}
          onOpenAutoFocus={(e) => e.preventDefault()}
          onCloseAutoFocus={(e) => e.preventDefault()}
          onInteractOutside={(e) => {
            if (anchorRef.current?.contains(e.target as Node)) e.preventDefault();
          }}
          className="z-50 w-[var(--radix-popover-trigger-width)] min-w-48 overflow-hidden rounded-lg border border-hairline bg-card shadow-card"
        >
          <ul id={listId} role="listbox" aria-multiselectable={multiple || undefined} aria-label={props["aria-label"]} className="max-h-64 overflow-y-auto p-1">
            {items.length === 0 ? (
              <li className="px-3 py-2 text-13 text-muted" role="presentation">
                {loading ? "Ищем…" : emptyText}
              </li>
            ) : (
              items.map((o, i) => {
                const sel = values.includes(o.value);
                return (
                  <li
                    key={`${o.value}-${o.isNew ? "new" : ""}`}
                    id={`${id}-opt-${i}`}
                    role="option"
                    aria-selected={sel}
                    aria-disabled={o.disabled || undefined}
                    data-active={i === active || undefined}
                    data-new={o.isNew || undefined}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => !o.disabled && setActive(i)}
                    onClick={() => pick(o)}
                    className="relative flex min-h-11 cursor-pointer items-center gap-2 rounded-md py-1.5 pl-8 pr-3 text-14 data-[active]:bg-tint-50 aria-disabled:cursor-not-allowed aria-disabled:opacity-50 sm:min-h-9"
                  >
                    {sel && <Check className="absolute left-2 size-4 text-brand-fg" aria-hidden />}
                    {o.isNew && o.hint ? (
                      <span className="text-brand-fg">{o.hint}</span>
                    ) : (
                      <>
                        <span className="min-w-0 flex-1 truncate">{o.label}</span>
                        {o.isNew && <span className="rounded-xs bg-tint-100 px-1 font-mono text-11 text-brand-fg">новый</span>}
                        {o.hint && <span className="shrink-0 font-mono text-12 text-muted">{o.hint}</span>}
                      </>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        </RPopover.Content>
      </RPopover.Portal>
    </RPopover.Root>
  );
}

export type SelectProps = Omit<ComboboxSingleProps, "multiple" | "searchable" | "loadOptions" | "creatable"> & {
  /** Поиск по списку (для длинных справочников). По умолчанию — от 8 вариантов. */
  searchable?: boolean;
};

/** Выбор одного значения из короткого списка. Свой выпадающий список вместо `<select>`, та же клавиатура. */
export function Select({ searchable, options = [], ...p }: SelectProps) {
  return <Combobox {...p} options={options} searchable={searchable ?? options.length >= 8} />;
}

/** Мультивыбор чипсами из статичного списка. */
export function MultiSelect(p: Omit<ComboboxMultiProps, "multiple">) {
  return <Combobox {...p} multiple />;
}
