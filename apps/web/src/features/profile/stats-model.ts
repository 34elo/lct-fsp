/** Чистые функции экрана «Статистика» (E38-2): точки «Где ты среди своих», просмотры по дням, история тестов. */
import type { ScatterPoint } from "@fsp/ui";

import type { AttemptOut, StandingPeer } from "@/api/model";

/**
 * Точки категории для ScatterPlot: X — сила 0–100, Y — ожидания (`salary_min`), нормированные по категории в 0–100.
 * Своя точка в `peers` первая (api.md, E35-12a). Без ожиданий — у нижней оси; одинаковые ожидания — посередине.
 */
export function scatter(peers: StandingPeer[], mine?: number | null): { points: ScatterPoint[]; you?: ScatterPoint } {
  const salaries = peers.map((p) => p.salary_min).filter((s): s is number => s != null);
  const lo = Math.min(...salaries);
  const hi = Math.max(...salaries);
  const y = (s: number | null | undefined) => (s == null ? 0 : hi > lo ? ((s - lo) / (hi - lo)) * 100 : 50);
  const pts = peers.map((p) => ({ x: p.strength * 100, y: y(p.salary_min) }));
  if (pts.length) return { points: pts.slice(1), you: pts[0] };
  return { points: [], you: mine != null ? { x: mine * 100, y: 0 } : undefined };
}

export interface ViewsStats {
  total: number;
  companies: number;
  byDay: { date: string; count: number }[];
}

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** Ответ `GET /candidates/me/views` (`{total_30d, companies_30d, by_day[{date, count}]}`; в OpenAPI без схемы). */
export function parseViews(raw: unknown): ViewsStats | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const r = raw as Record<string, unknown>;
  const byDay = Array.isArray(r.by_day)
    ? r.by_day.flatMap((d) => {
        const o = d as Record<string, unknown> | null;
        return o && typeof o.date === "string" ? [{ date: o.date, count: num(o.count) }] : [];
      })
    : [];
  return { total: num(r.total_30d), companies: num(r.companies_30d), byDay };
}

/** Просмотры по дням для тепловой карты: `weeks` полных недель, последний день — `today` (UTC), от старых к новым. */
export function viewsSeries(byDay: { date: string; count: number }[], today: Date, weeks = 5): number[] {
  const map = new Map(byDay.map((d) => [d.date.slice(0, 10), d.count]));
  const days = weeks * 7;
  const end = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Array.from({ length: days }, (_, i) => map.get(new Date(end - (days - 1 - i) * 86_400_000).toISOString().slice(0, 10)) ?? 0);
}

/** История тестов: завершённые попытки, новые выше. */
export function finishedAttempts(attempts: AttemptOut[]): AttemptOut[] {
  return attempts
    .filter((a) => a.status === "passed" || a.status === "failed")
    .sort((a, b) => (b.finished_at ?? b.started_at).localeCompare(a.finished_at ?? a.started_at));
}
