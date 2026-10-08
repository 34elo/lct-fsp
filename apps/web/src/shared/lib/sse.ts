import type { QueryClient } from "@tanstack/react-query";

/** Типы SSE-событий из api.md §4. */
export const SSE_EVENTS = [
  "job.progress",
  "resume.parsed",
  "resume.failed",
  "fsp.imported",
  "code.analysis.completed",
  "profile.updated",
  "offer.created",
  "offer.updated",
  "offer.message",
  "matches.ready",
  "matches.rationale_ready",
  "notification.new",
] as const;
export type SseEventType = (typeof SSE_EVENTS)[number];

export interface SseMessage {
  type: SseEventType;
  data: unknown;
}

export interface EventStreamOptions {
  url: string;
  getToken: () => string | null;
  onMessage: (m: SseMessage) => void;
  /** Фабрика нужна для тестов; по умолчанию нативный EventSource. */
  create?: (url: string) => EventSource;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

/**
 * Один EventSource на вкладку. При ошибке закрываем и переподключаемся с
 * экспоненциальной паузой (с новым токеном в query), успешное открытие сбрасывает паузу.
 */
export function createEventStream(opts: EventStreamOptions) {
  const { baseDelayMs = 1000, maxDelayMs = 30000 } = opts;
  const create = opts.create ?? ((u: string) => new EventSource(u));
  let es: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let attempt = 0;
  let stopped = false;

  const connect = () => {
    if (stopped) return;
    const token = opts.getToken();
    const url = token ? `${opts.url}?access_token=${encodeURIComponent(token)}` : opts.url;
    es = create(url);
    es.onopen = () => {
      attempt = 0;
    };
    for (const type of SSE_EVENTS) {
      es.addEventListener(type, (e) => {
        let data: unknown = null;
        try {
          data = JSON.parse((e as MessageEvent<string>).data);
        } catch {
          /* битый JSON игнорируем */
          return;
        }
        opts.onMessage({ type, data });
      });
    }
    es.onerror = () => {
      es?.close();
      es = null;
      if (stopped) return;
      const delay = Math.min(baseDelayMs * 2 ** attempt, maxDelayMs);
      attempt += 1;
      timer = setTimeout(connect, delay);
    };
  };

  connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    es?.close();
    es = null;
  };
}

/** Инвалидация кешей по событиям (frontend.md §4). Ключи уточнятся с генерацией клиента. */
export function invalidateFor(qc: QueryClient, m: SseMessage) {
  const d = (m.data ?? {}) as { offer_id?: string; vacancy_id?: string };
  switch (m.type) {
    case "profile.updated":
    case "fsp.imported":
    case "resume.parsed":
    case "code.analysis.completed":
      void qc.invalidateQueries({ queryKey: ["profile"] });
      // Ключи orval — пути запросов: профиль и обзор ФСП перечитываем по ним.
      void qc.invalidateQueries({
        predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith("/candidates/me/"),
      });
      break;
    case "offer.created":
    case "offer.updated":
    case "offer.message":
      void qc.invalidateQueries({ queryKey: d.offer_id ? ["offers", d.offer_id] : ["offers"] });
      void qc.invalidateQueries({ queryKey: ["offers"] });
      break;
    case "matches.ready":
    case "matches.rationale_ready":
      void qc.invalidateQueries({ queryKey: ["matches", d.vacancy_id] });
      break;
    case "notification.new":
      void qc.invalidateQueries({ queryKey: ["notifications"] });
      break;
    default:
      break;
  }
}
