import { Input } from "@fsp/ui";

import { cn } from "@/shared/lib/cn";
import { move, parseListing, splitStem, toggleLine, type AnswerValue, type TestItem } from "./model";
import { T } from "./text";

const Code = ({ children }: { children: string }) => (
  <pre className="overflow-x-auto rounded-lg border border-hairline bg-tint-50 p-3 font-mono text-13 leading-relaxed">{children}</pre>
);

/** Поле ответа одного задания (или шага цепочки). Правильность не показывается никогда. */
export function Question({
  item,
  value,
  onChange,
  disabled,
  idPrefix = "q",
}: {
  item: TestItem;
  value: AnswerValue;
  onChange: (v: AnswerValue) => void;
  disabled?: boolean;
  idPrefix?: string;
}) {
  const opts = item.options ?? [];

  switch (item.kind) {
    case "exact": {
      const { prose, code } = splitStem(item.stem);
      return (
        <div className="flex flex-col gap-3">
          <p className="whitespace-pre-line text-16">{prose}</p>
          {code && <Code>{code}</Code>}
          <label className="flex flex-col gap-1.5 text-14 font-medium" htmlFor={`${idPrefix}-exact`}>
            {T.exactLabel}
            <Input
              id={`${idPrefix}-exact`}
              value={typeof value === "string" ? value : ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              autoComplete="off"
              data-testid="assessment-input-exact"
            />
            <span className="text-12 font-normal text-muted">{T.exactHint}</span>
          </label>
        </div>
      );
    }
    case "estimate":
      return (
        <div className="flex flex-col gap-3">
          <p className="whitespace-pre-line text-16">{item.stem}</p>
          <label className="flex flex-col gap-1.5 text-14 font-medium" htmlFor={`${idPrefix}-estimate`}>
            {T.estimateLabel}
            <Input
              id={`${idPrefix}-estimate`}
              inputMode="decimal"
              value={typeof value === "string" ? value : ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              autoComplete="off"
              data-testid="assessment-input-estimate"
            />
            <span className="text-12 font-normal text-muted">{T.estimateHint}</span>
          </label>
        </div>
      );
    case "choice":
      return (
        <div className="flex flex-col gap-3">
          <p className="whitespace-pre-line text-16">{item.stem}</p>
          <div role="radiogroup" aria-label={item.stem} className="flex flex-col gap-2">
            {opts.map((o, i) => (
              <label
                key={i}
                className={cn(
                  "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border bg-card p-3 text-14",
                  value === i ? "border-brand bg-tint-50" : "border-hairline hover:border-brand-mid",
                )}
              >
                <input
                  type="radio"
                  name={`${idPrefix}-choice`}
                  className="mt-0.5 size-4 accent-[var(--brand)]"
                  checked={value === i}
                  onChange={() => onChange(i)}
                  disabled={disabled}
                  data-testid={`assessment-option-${i}`}
                />
                <span>{o}</span>
              </label>
            ))}
          </div>
        </div>
      );
    case "find_bug": {
      const { prose, lines } = parseListing(item.stem);
      const chosen = Array.isArray(value) ? value : [];
      return (
        <div className="flex flex-col gap-3">
          <p className="whitespace-pre-line text-16">{prose}</p>
          <ul className="overflow-x-auto rounded-lg border border-hairline bg-tint-50 font-mono text-13" data-testid="assessment-listing">
            {lines.map((l) => {
              const on = chosen.includes(l.no);
              return (
                <li key={l.no}>
                  <button
                    type="button"
                    aria-pressed={on}
                    aria-label={`Строка ${l.no}`}
                    disabled={disabled}
                    onClick={() => onChange(toggleLine(chosen, l.no))}
                    data-testid={`assessment-line-${l.no}`}
                    className={cn(
                      "flex min-h-11 w-full items-center gap-3 px-3 text-left sm:min-h-8",
                      on ? "bg-brand text-on-brand" : "hover:bg-tint-100",
                    )}
                  >
                    <span className="w-6 shrink-0 text-right opacity-70">{l.no}</span>
                    <span className="whitespace-pre">{l.text}</span>
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="text-12 text-muted" data-testid="assessment-find-hint">
            {T.findBugHint(chosen.length)}
          </p>
        </div>
      );
    }
    case "order":
    case "sjt": {
      const order = Array.isArray(value) ? value : opts.map((_, i) => i);
      return (
        <div className="flex flex-col gap-3">
          <p className="whitespace-pre-line text-16">{item.stem}</p>
          <p className="text-12 text-muted">{item.kind === "sjt" ? T.sjtHint : T.orderHint}</p>
          <ol className="flex flex-col gap-2" data-testid="assessment-order">
            {order.map((idx, pos) => (
              <li key={idx} className="flex items-center gap-2 rounded-lg border border-hairline bg-card p-2 text-14">
                <span className="w-6 shrink-0 text-center font-mono text-muted">{pos + 1}</span>
                <span className="flex-1">{opts[idx]}</span>
                <button
                  type="button"
                  aria-label={T.moveUp(opts[idx] ?? "")}
                  disabled={disabled || pos === 0}
                  onClick={() => onChange(move(order, pos, -1))}
                  data-testid={`assessment-up-${pos}`}
                  className="grid size-11 place-items-center rounded-md hover:bg-tint-50 disabled:opacity-40 sm:size-8"
                >
                  <span aria-hidden>↑</span>
                </button>
                <button
                  type="button"
                  aria-label={T.moveDown(opts[idx] ?? "")}
                  disabled={disabled || pos === order.length - 1}
                  onClick={() => onChange(move(order, pos, 1))}
                  data-testid={`assessment-down-${pos}`}
                  className="grid size-11 place-items-center rounded-md hover:bg-tint-50 disabled:opacity-40 sm:size-8"
                >
                  <span aria-hidden>↓</span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      );
    }
    default:
      return <p className="whitespace-pre-line text-16">{item.stem}</p>;
  }
}
