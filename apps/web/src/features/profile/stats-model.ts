/** Чистые функции экрана «Статистика» (E38-2): точки «Где ты среди своих», просмотры по дням, история тестов. */
import type { ScatterPoint } from "@fsp/ui";

import type { AttemptOut, StandingPeer } from "@/api/model";

/**
 * Точки категории для ScatterPlot (E39-16): X — уровень в тесте θ, нормированный по категории в 0–100;
 * Y — сила профиля 0–100. Своя точка в `peers` первая (api.md, E35-12a). Без θ у участников X — сила;
 * одинаковая θ у всех — посередине.
 */
export function scatter(peers: StandingPeer[], mine?: number | null): { points: ScatterPoint[]; you?: ScatterPoint } {
  const thetas = peers.map((p) => p.theta).filter((t): t is number => t != null);
  const lo = Math.min(...thetas);
  const hi = Math.max(...thetas);
  const x = (p: StandingPeer) => (p.theta == null ? p.strength * 100 : hi > lo ? ((p.theta - lo) / (hi - lo)) * 100 : 50);
  const pts = peers.map((p) => ({ x: x(p), y: p.strength * 100 }));
  if (pts.length) return { points: pts.slice(1), you: pts[0] };
  return { points: [], you: mine != null ? { x: mine * 100, y: mine * 100 } : undefined };
}

export interface ViewsStats {
  total: number;
  companies: number;
  /** Карточка доступна работодателям (тест + согласие на публикацию); без неё нули ожидаемы (E43-5). */
  visible: boolean;
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
  return { total: num(r.total_30d), companies: num(r.companies_30d), visible: r.visible !== false, byDay };
}

/** Состояние без просмотров: ответ не пришёл или нулевая статистика (полная шкала с нулями, E43-5). */
export const NO_VIEWS: ViewsStats = { total: 0, companies: 0, visible: true, byDay: [] };

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
