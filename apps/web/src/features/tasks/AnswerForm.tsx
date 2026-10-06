import { Checkbox, Input, Textarea, cn } from "@fsp/ui";

import { TASKS_TEXT as T } from "./text";
import { moveItem, type AnswerState, type TaskItem } from "./model";

type Props = { item: TaskItem; value: AnswerState; onChange: (v: AnswerState) => void; disabled?: boolean; id: string };

/** Поле ответа по типу задания; для chain — по полю на шаг. */
export function AnswerField({ item, value, onChange, disabled, id }: Props) {
  const options = item.options ?? [];
  switch (item.kind) {
    case "choice":
      return (
        <div role="radiogroup" aria-label={T.answerLabel} className="grid gap-2" data-testid="tasks-choice">
          {options.map((o, i) => (
            <label key={i} className={cn("flex min-h-12 cursor-pointer items-center gap-3 rounded-lg border p-3 text-14", value === i ? "border-brand bg-tint-50" : "border-hairline")}>
              <input type="radio" name={id} checked={value === i} disabled={disabled} onChange={() => onChange(i)} className="accent-brand" />
              {o}
            </label>
          ))}
        </div>
      );
    case "find_bug": {
      const sel = (value as number[]) ?? [];
      return (
        <div className="grid gap-2" data-testid="tasks-find-bug">
          {options.map((o, i) => (
            <label key={i} className="flex min-h-12 items-center gap-3 rounded-lg border border-hairline p-3 text-14">
              <Checkbox
                checked={sel.includes(i)}
                disabled={disabled}
                onCheckedChange={(c) => onChange(c ? [...sel, i] : sel.filter((x) => x !== i))}
                aria-label={o}
              />
              <span className="font-mono">{o}</span>
            </label>
          ))}
        </div>
      );
    }
    case "order":
    case "sjt": {
      const order = (value as number[]) ?? [];
      return (
        <ol className="grid gap-2" data-testid="tasks-order">
          {order.map((idx, pos) => (
            <li key={idx} className="flex items-center gap-2 rounded-lg border border-hairline p-2 text-14">
              <span className="w-6 text-center font-mono text-muted">{pos + 1}</span>
              <span className="min-w-0 flex-1 break-words">{options[idx]}</span>
              <button type="button" disabled={disabled || pos === 0} aria-label={`${T.moveUp}: ${options[idx]}`} onClick={() => onChange(moveItem(order, pos, -1))} className="h-10 w-10 rounded-lg border border-hairline disabled:opacity-40">↑</button>
              <button type="button" disabled={disabled || pos === order.length - 1} aria-label={`${T.moveDown}: ${options[idx]}`} onClick={() => onChange(moveItem(order, pos, 1))} className="h-10 w-10 rounded-lg border border-hairline disabled:opacity-40">↓</button>
            </li>
          ))}
        </ol>
      );
    }
    case "open":
      return <Textarea rows={6} value={String(value ?? "")} disabled={disabled} placeholder={T.openPlaceholder} aria-label={T.answerLabel} onChange={(e) => onChange(e.target.value)} data-testid="tasks-answer-input" />;
    case "chain": {
      const steps = item.steps ?? [];
      const vals = (value as AnswerState[]) ?? [];
      return (
        <div className="grid gap-4" data-testid="tasks-chain">
          {steps.map((st, i) => (
            <div key={i} className="grid gap-2">
              <p className="font-mono text-12 font-semibold text-muted">{T.stepN(i + 1)}</p>
              <p className="text-14">{st.stem}</p>
              <AnswerField id={`${id}-${i}`} item={st} disabled={disabled} value={vals[i] ?? null} onChange={(v) => onChange(vals.map((x, j) => (j === i ? v : x)))} />
            </div>
          ))}
        </div>
      );
    }
    default:
      return <Input value={String(value ?? "")} disabled={disabled} aria-label={T.answerLabel} onChange={(e) => onChange(e.target.value)} data-testid="tasks-answer-input" />;
  }
}
