import { useSearchParams } from "react-router-dom";

import { cn } from "@fsp/ui";

/** Значение фильтра `?show=` из адреса: неизвестное — первое. */
export function useShow<K extends string>(keys: readonly K[]): K {
  const v = useSearchParams()[0].get("show");
  return keys.find((k) => k === v) ?? keys[0];
}

/**
 * Фильтр «Приглашения · Интересы · Отклики» внутри страницы (E39-25): вместо второй строки вкладок под шапкой.
 * Первый вариант — без параметра в адресе.
 */
export function ShowFilter<K extends string>({ options, label }: { options: Record<K, string>; label: string }) {
  const keys = Object.keys(options) as K[];
  const value = useShow(keys);
  const [, setParams] = useSearchParams();
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {keys.map((k) => (
        <button
          key={k}
          type="button"
          aria-pressed={value === k}
          onClick={() => setParams(k === keys[0] ? {} : { show: k }, { replace: true })}
          className={cn(
            "min-h-11 rounded-full border px-4 text-13 font-semibold",
            value === k ? "border-brand bg-tint-50 text-brand-fg" : "border-hairline text-muted hover:bg-tint-50",
          )}
        >
          {options[k]}
        </button>
      ))}
    </div>
  );
}
