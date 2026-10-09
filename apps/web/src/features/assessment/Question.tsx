import { CodeLines, Input, Lbl, Markdown, OptionRow } from "@fsp/ui";
import { useState } from "react";

import { hasTable, move, moveTo, parseListing, splitStem, toggleLine, type AnswerValue, type TestItem } from "./model";
import { T } from "./text";

/**
 * Условие задания: обычный вес, размер по длине (длинное — мельче). Если в условии есть таблица,
 * весь текст идёт через Markdown (GFM, без исполнения HTML); таблица прокручивается внутри себя.
 */
const Stem = ({ children }: { children: string }) => {
  const n = children.length;
  const size = n <= 140 ? "text-16 leading-[1.4] md:text-20" : n <= 320 ? "text-16 leading-[1.45]" : "text-14 leading-[1.5] md:text-16";
  if (hasTable(children)) {
    return (
      <Markdown className={`${size} font-normal`} data-testid="assessment-stem">
        {children}
      </Markdown>
    );
  }
  return (
    <h2 className={`m-0 font-mono font-normal whitespace-pre-line ${size}`} data-testid="assessment-stem">
      {children}
    </h2>
  );
};

const Code = ({ children }: { children: string }) => <CodeLines lines={children.split("\n")} label="Код задания" />;

const arrow =
  "grid size-11 flex-none place-items-center rounded-md text-muted hover:bg-tint-50 hover:text-ink disabled:opacity-40 sm:size-9";

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
  // Для order/sjt: какая строка «взята» кликом, чтобы поставить её на другое место.
  const [picked, setPicked] = useState<number | null>(null);

  switch (item.kind) {
    case "exact": {
      const { prose, code } = splitStem(item.stem);
      return (
        <div className="flex flex-col gap-4">
          <Stem>{prose}</Stem>
          {code && <Code>{code}</Code>}
          <div className="flex flex-col gap-1.5">
            <Lbl>
              <label htmlFor={`${idPrefix}-exact`}>{T.exactLabel}</label>
            </Lbl>
            <Input
              id={`${idPrefix}-exact`}
              value={typeof value === "string" ? value : ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              autoComplete="off"
              className="font-mono text-16"
              data-testid="assessment-input-exact"
            />
            <span className="text-12 text-muted">{T.exactHint}</span>
          </div>
        </div>
      );
    }
    case "estimate":
      return (
        <div className="flex flex-col gap-4">
          <Stem>{item.stem}</Stem>
          <div className="flex flex-col gap-1.5">
            <Lbl>
              <label htmlFor={`${idPrefix}-estimate`}>{T.estimateLabel}</label>
            </Lbl>
            <Input
              id={`${idPrefix}-estimate`}
              inputMode="decimal"
              value={typeof value === "string" ? value : ""}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              autoComplete="off"
              className="font-mono text-16"
              data-testid="assessment-input-estimate"
            />
            <span className="text-12 text-muted">{T.estimateHint}</span>
          </div>
        </div>
      );
    case "choice": {
      const { prose, code } = splitStem(item.stem);
      return (
        <div className="flex flex-col gap-4">
          <Stem>{prose}</Stem>
          {code && <Code>{code}</Code>}
          <div role="radiogroup" aria-label={prose} className="flex flex-col gap-2">
            {opts.map((o, i) => (
              <OptionRow
                key={i}
                kind="choice"
                selected={value === i}
                disabled={disabled}
                onClick={() => onChange(i)}
                data-testid={`assessment-option-${i}`}
              >
                {o}
              </OptionRow>
            ))}
          </div>
        </div>
      );
    }
    case "find_bug": {
      const { prose, lines } = parseListing(item.stem);
      const chosen = Array.isArray(value) ? value : [];
      const nos = lines.map((l) => l.no);
      return (
        <div className="flex flex-col gap-4">
          <Stem>{prose}</Stem>
          <div data-testid="assessment-listing">
            <CodeLines
              lines={lines.map((l) => l.text)}
              start={nos[0] ?? 1}
              selected={chosen.flatMap((no) => {
                const at = nos.indexOf(no);
                return at < 0 ? [] : [at];
              })}
              onSelect={disabled ? undefined : (i) => onChange(toggleLine(chosen, nos[i]!))}
              lineTestId={(no) => `assessment-line-${no}`}
              label="Код: выберите строки с ошибкой"
            />
          </div>
          <p className="text-12 text-muted" data-testid="assessment-find-hint">
            {T.findBugHint(chosen.length)}
          </p>
        </div>
      );
    }
    case "order":
    case "sjt": {
      const order = Array.isArray(value) ? value : opts.map((_, i) => i);
      const kind = item.kind;
      const put = (to: number) => {
        if (picked === null) return setPicked(to);
        if (picked !== to) onChange(moveTo(order, picked, to));
        setPicked(null);
      };
      return (
        <div className="flex flex-col gap-4">
          <Stem>{item.stem}</Stem>
          <p className="text-12 text-muted">
            {kind === "sjt" ? T.sjtHint : T.orderHint} {T.orderPick}
          </p>
          <ol className="m-0 flex list-none flex-col gap-2 p-0" data-testid="assessment-order">
            {order.map((idx, pos) => (
              <li key={idx} className="flex items-center gap-1">
                <OptionRow
                  kind={kind}
                  index={pos + 1}
                  selected={picked === pos}
                  dragging={picked === pos}
                  disabled={disabled}
                  onClick={() => put(pos)}
                  className="flex-1"
                  data-testid={`assessment-row-${pos}`}
                >
                  {opts[idx] ?? ""}
                </OptionRow>
                <button
                  type="button"
                  aria-label={T.moveUp(opts[idx] ?? "")}
                  disabled={disabled || pos === 0}
                  onClick={() => {
                    setPicked(null);
                    onChange(move(order, pos, -1));
                  }}
                  data-testid={`assessment-up-${pos}`}
                  className={arrow}
                >
                  <span aria-hidden>↑</span>
                </button>
                <button
                  type="button"
                  aria-label={T.moveDown(opts[idx] ?? "")}
                  disabled={disabled || pos === order.length - 1}
                  onClick={() => {
                    setPicked(null);
                    onChange(move(order, pos, 1));
                  }}
                  data-testid={`assessment-down-${pos}`}
                  className={arrow}
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
      return <Stem>{item.stem}</Stem>;
  }
}
