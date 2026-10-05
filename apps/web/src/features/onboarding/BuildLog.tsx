import { cn } from "@/shared/lib/cn";

export interface LogLine {
  id: string;
  text: string;
  state: "done" | "active" | "fail";
}

const MARK: Record<LogLine["state"], string> = { done: "✓", active: "◌", fail: "✕" };

/** Терминальный лог этапов долгой задачи (frontend.md §6). Строки приходят снаружи, компонент только рисует. */
export function BuildLog({ title, lines, className }: { title: string; lines: LogLine[]; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-hairline bg-tint-50 p-3 font-mono text-[13px] leading-6", className)}>
      <p className="text-muted">$ {title}</p>
      <ul role="log" aria-live="polite" aria-label={title} className="flex flex-col">
        {lines.map((l) => (
          <li
            key={l.id}
            className={cn(
              "fsp-log-line flex gap-2",
              l.state === "done" && "text-brand-deep",
              l.state === "active" && "text-ink",
              l.state === "fail" && "text-error",
            )}
          >
            <span aria-hidden className={cn(l.state === "active" && "fsp-spin")}>
              {MARK[l.state]}
            </span>
            <span>{l.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
