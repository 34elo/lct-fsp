import { NavLink } from "react-router-dom";

import { T } from "./text";

const ITEMS = [
  { to: "/admin/quality", label: T.nav.quality, end: true },
  { to: "/admin/quality/fairness", label: T.nav.fairness, end: false },
  { to: "/admin/quality/runs", label: T.nav.runs, end: false },
];

/** Переключатель разделов страницы качества (Q1–Q3). */
export function QualityNav() {
  return (
    <nav aria-label={T.navLabel} className="flex flex-wrap gap-2">
      {ITEMS.map((i) => (
        <NavLink
          key={i.to}
          to={i.to}
          end={i.end}
          className={({ isActive }) =>
            `rounded-lg border px-3 py-1.5 text-14 font-semibold ${isActive ? "border-brand-fg bg-card text-brand-fg" : "border-hairline text-muted"}`
          }
        >
          {i.label}
        </NavLink>
      ))}
    </nav>
  );
}
