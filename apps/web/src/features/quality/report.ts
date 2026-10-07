import raw from "./metrics.generated.json";

export type Status = "green" | "yellow" | "red" | "unmeasured" | "info";

export interface MetricRow {
  area: string;
  id: string;
  name: string;
  note: string;
  source: string;
  status: Status;
  value_text: string;
  target_text: string;
}

export interface MetricsReport {
  seed: number;
  summary: Record<Status, number>;
  components: Record<string, { ok: boolean; reason: string }>;
  rows: MetricRow[];
}

/** Копия `reports/metrics/report.json`; обновляется командой `make metrics`. */
export const report = raw as unknown as MetricsReport;

export const STATUS_ORDER: Status[] = ["green", "yellow", "red", "unmeasured", "info"];

export function byArea(rows: MetricRow[]): [string, MetricRow[]][] {
  const m = new Map<string, MetricRow[]>();
  for (const r of rows) m.set(r.area, [...(m.get(r.area) ?? []), r]);
  return [...m.entries()];
}
