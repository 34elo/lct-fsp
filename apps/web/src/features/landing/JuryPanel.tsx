import { useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { juryEnabled } from "./jury";
import { PANEL, T } from "./text";

/** Панель «что попробовать»: 5 шагов сценария, видна в кабинетах только при `VITE_JURY_MODE=true`. */
export function JuryPanel() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(true);
  if (!juryEnabled()) return null;
  const current = PANEL.steps.findIndex((s) => pathname.startsWith(s.to.split("?")[0]));
  return (
    <aside
      aria-label={PANEL.title}
      data-testid="jury-panel"
      className="fixed bottom-20 right-4 z-40 w-[min(320px,calc(100vw-2rem))] rounded-xl border border-hairline bg-card p-3 shadow-lg md:bottom-4"
    >
      <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex w-full items-center justify-between font-mono text-14 font-semibold">
        {PANEL.title}
        <span className="text-12 text-muted">{open ? T.juryHide : T.juryShow}</span>
      </button>
      {open && (
        <ol className="mt-2 flex flex-col gap-2 text-13">
          {PANEL.steps.map((s, i) => (
            <li key={s.to} aria-current={i === current ? "step" : undefined} className={i === current ? "font-semibold text-ink" : "text-muted"}>
              <Link to={s.to} className="underline-offset-2 hover:underline">
                {i + 1}. {s.label}
              </Link>
              <span className="block text-12 text-muted">{s.who}</span>
            </li>
          ))}
        </ol>
      )}
    </aside>
  );
}
