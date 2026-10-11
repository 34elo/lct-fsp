import type { ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { InfoTip } from "@fsp/ui";

import { WHY } from "./text";

/**
 * Шапка страницы админки: заголовок с ⓘ и подзаголовок «зачем».
 * Подзаголовок берётся из `WHY` по адресу страницы (или `path`), ⓘ — подробности страницы:
 * что делаете вы и что работает само. `children` — действия справа (период, фильтр).
 */
export function AdminPageHeader({ title, tip, path, children }: { title: string; tip: ReactNode; path?: string; children?: ReactNode }) {
  const { pathname } = useLocation();
  const why = WHY[path ?? pathname];
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex items-center gap-2">
          <h1 className="min-w-0 text-24 font-semibold">{title}</h1>
          <InfoTip title={title} label={`Подробнее о странице «${title}»`} data-testid="page-tip">
            {tip}
          </InfoTip>
        </div>
        {why && (
          <p className="max-w-3xl text-14 text-muted" data-testid="page-why">
            {why}
          </p>
        )}
      </div>
      {children}
    </header>
  );
}
