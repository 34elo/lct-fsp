import { cn } from "@fsp/ui";

/** Переключатель вкладок-фильтров со счётчиками. */
export function FilterTabs({ tabs, value, counts, onChange, label }: { tabs: Record<string, string>; value: string; counts: Record<string, number>; onChange: (v: string) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {Object.entries(tabs).map(([k, name]) => (
        <button
          key={k}
          type="button"
          aria-pressed={value === k}
          onClick={() => onChange(k)}
          className={cn("h-9 rounded-lg border px-3 font-mono text-13", value === k ? "border-brand bg-tint-50 text-brand-fg" : "border-hairline text-muted hover:bg-tint-50")}
        >
          {name} ({counts[k] ?? 0})
        </button>
      ))}
    </div>
  );
}
