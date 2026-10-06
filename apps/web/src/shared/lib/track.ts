import { API_BASE } from "@/api/mutator";
import { getAccessToken } from "@/shared/lib/token";

/** Трекер событий интерфейса (metrics.md §2.1): очередь, батч раз в 5 с, sendBeacon при уходе. */

export const MAX_BATCH = 50;
export const FLUSH_MS = 5000;
export const SESSION_IDLE_MS = 30 * 60 * 1000;
const MAX_QUEUE = 500;

const RUN_KEY = "fsp_run_id";
let runId: string | null = null;

/** Метка живого прогона (metrics.md §3): все события вкладки получают `run_id`. Живёт в sessionStorage вкладки. */
export function setRunId(id: string | null) {
  runId = id;
  try {
    if (id) sessionStorage.setItem(RUN_KEY, id);
    else sessionStorage.removeItem(RUN_KEY);
  } catch {
    // приватный режим: метка живёт только в памяти
  }
}

export function getRunId(): string | null {
  if (runId) return runId;
  try {
    return sessionStorage.getItem(RUN_KEY);
  } catch {
    return null;
  }
}

export type TrackProps = Record<string, string | number | boolean | null | undefined>;

interface QueuedEvent {
  event: string;
  ts: string;
  session_id: string;
  run_id?: string;
  app_version?: string;
  props: Record<string, string | number | boolean>;
}

export interface TrackerOptions {
  url?: string;
  getToken?: () => string | null;
  /** Подмена отправки для тестов; по умолчанию fetch с Bearer-токеном. */
  send?: (url: string, body: string) => Promise<unknown>;
  beacon?: (url: string, body: Blob) => boolean;
  now?: () => number;
  appVersion?: string;
  flushMs?: number;
}

const rid = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
const sessionId = () => `s_${rid().replace(/-/g, "").slice(0, 24)}`;

/** `session_id`: 30 минут бездействия = новая сессия. */
function makeSession(now: () => number) {
  let id = sessionId();
  let last = now();
  return () => {
    const t = now();
    if (t - last > SESSION_IDLE_MS) id = sessionId();
    last = t;
    return id;
  };
}

export function createTracker(opts: TrackerOptions = {}) {
  const url = opts.url ?? `${API_BASE}/track`;
  const getToken = opts.getToken ?? getAccessToken;
  const now = opts.now ?? Date.now;
  const send =
    opts.send ??
    ((u: string, body: string) => {
      const token = getToken();
      return fetch(u, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body,
        credentials: "include",
        keepalive: true,
      });
    });
  const beacon = opts.beacon ?? ((u: string, b: Blob) => navigator.sendBeacon(u, b));
  const session = makeSession(now);
  let queue: QueuedEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;

  const clean = (props: TrackProps) => {
    const out: Record<string, string | number | boolean> = {};
    for (const [k, v] of Object.entries(props)) if (v !== null && v !== undefined) out[k] = v;
    return out;
  };

  const take = () => {
    const events = queue.slice(0, MAX_BATCH);
    queue = queue.slice(MAX_BATCH);
    return events;
  };

  async function flush() {
    clearTimeout(timer);
    timer = undefined;
    while (queue.length) {
      const body = JSON.stringify({ events: take(), batch_id: rid() });
      try {
        await send(url, body);
      } catch {
        // аналитика не должна ломать интерфейс; потерянный батч не повторяем
      }
    }
  }

  /** Уход со страницы: sendBeacon не умеет заголовки, токен для псевдонима идёт в теле. */
  function flushBeacon() {
    clearTimeout(timer);
    timer = undefined;
    while (queue.length) {
      const body = JSON.stringify({ events: take(), batch_id: rid(), access_token: getToken() ?? undefined });
      try {
        beacon(url, new Blob([body], { type: "application/json" }));
      } catch {
        // ignore
      }
    }
  }

  function track(event: string, props: TrackProps = {}) {
    if (queue.length >= MAX_QUEUE) queue.shift();
    queue.push({
      event,
      ts: new Date(now()).toISOString(),
      session_id: session(),
      ...(getRunId() ? { run_id: getRunId()! } : {}),
      ...(opts.appVersion ? { app_version: opts.appVersion } : {}),
      props: clean(props),
    });
    if (queue.length >= MAX_BATCH) void flush();
    else timer ??= setTimeout(() => void flush(), opts.flushMs ?? FLUSH_MS);
  }

  return { track, flush, flushBeacon, size: () => queue.length };
}

export type Tracker = ReturnType<typeof createTracker>;

let shared: Tracker | null = null;

/** Один трекер на вкладку; слушатели ухода со страницы ставятся при первом обращении. */
export function getTracker(): Tracker {
  if (!shared) {
    shared = createTracker();
    const t = shared;
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") t.flushBeacon();
    });
    window.addEventListener("pagehide", () => t.flushBeacon());
  }
  return shared;
}
