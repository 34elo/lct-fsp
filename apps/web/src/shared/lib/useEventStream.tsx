import { useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";

import { API_BASE } from "@/api/mutator";
import { useAuth } from "@/shared/lib/auth";
import { createEventStream, invalidateFor, type SseEventType, type SseMessage } from "@/shared/lib/sse";
import { getAccessToken } from "@/shared/lib/token";

type Handler = (m: SseMessage) => void;
const Ctx = createContext<{ subscribe(h: Handler): () => void } | null>(null);

/** Корневой провайдер: один поток на вкладку, только для вошедшего пользователя. */
export function EventStreamProvider({ children, url = `${API_BASE}/events/stream` }: { children: ReactNode; url?: string }) {
  const qc = useQueryClient();
  const { status } = useAuth();
  const handlers = useRef(new Set<Handler>());
  const api = useRef({
    subscribe(h: Handler) {
      handlers.current.add(h);
      return () => {
        handlers.current.delete(h);
      };
    },
  });

  useEffect(() => {
    if (status !== "authenticated") return;
    return createEventStream({
      url,
      getToken: getAccessToken,
      onMessage: (m) => {
        invalidateFor(qc, m);
        handlers.current.forEach((h) => h(m));
      },
    });
  }, [status, url, qc]);

  return <Ctx.Provider value={api.current}>{children}</Ctx.Provider>;
}

/** Подписка на события потока; без `types` — на все. */
export function useEventStream(onEvent: Handler, types?: SseEventType[]) {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useEventStream вне EventStreamProvider");
  const cb = useRef(onEvent);
  cb.current = onEvent;
  const key = types?.join(",");
  useEffect(
    () => ctx.subscribe((m) => (!types || types.includes(m.type)) && cb.current(m)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ctx, key],
  );
}
