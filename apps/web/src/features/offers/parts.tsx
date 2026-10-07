import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  useListEventsOffersOfferIdEventsGet,
  useListMessagesOffersOfferIdMessagesGet,
  usePostMessageOffersOfferIdMessagesPost,
} from "@/api/endpoints/offers/offers";
import type { MessageOut } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { Button } from "@/shared/ui/button";
import { cn } from "@/shared/lib/cn";
import { ACTOR_LABEL, dateTime, OFFER_STATUS_LABEL, offerErrorText, statusTone } from "./text";

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={cn("whitespace-nowrap rounded-md px-2 py-1 text-xs font-semibold", statusTone(status))}>
      {OFFER_STATUS_LABEL[status] ?? status}
    </span>
  );
}

export function Panel({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={title} className={cn("flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4 md:p-5", className)}>
      <h2 className="font-mono text-[17px] font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** Таймлайн переходов (offer_events): без payload, только «кто, во что, когда». */
export function Timeline({ offerId }: { offerId: string }) {
  const q = useListEventsOffersOfferIdEventsGet(offerId);
  const events = q.data?.status === 200 ? q.data.data : [];
  return (
    <Panel title="История">
      {q.isPending && <p role="status" className="text-sm text-muted">Загрузка…</p>}
      <ol className="flex flex-col gap-2 border-l border-hairline pl-4">
        {events.map((e) => (
          <li key={e.id} className="relative text-sm">
            <span aria-hidden className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-brand" />
            <b>{OFFER_STATUS_LABEL[e.to_status] ?? e.to_status}</b>{" "}
            <span className="text-muted">· {ACTOR_LABEL[e.actor] ?? e.actor} · {dateTime(e.created_at)}</span>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

/** Переписка по приглашению. `side` — кто мы, чтобы подписать «Вы». */
export function Conversation({ offerId, side, canWrite }: { offerId: string; side: "candidate" | "company"; canWrite: boolean }) {
  const qc = useQueryClient();
  const q = useListMessagesOffersOfferIdMessagesGet(offerId, { query: { refetchInterval: 15_000 } });
  const [text, setText] = useState("");
  const post = usePostMessageOffersOfferIdMessagesPost({
    mutation: {
      onSuccess: (r) => {
        setText("");
        // Сервер коммитит после ответа: мгновенный refetch может прийти раньше записи, поэтому
        // сразу кладём новое сообщение в кеш, а сверку делаем чуть позже.
        qc.setQueryData([`/offers/${offerId}/messages`], (old: { data: MessageOut[]; status: number; headers: Headers } | undefined) =>
          old && r.status === 201 ? { ...old, data: [...old.data, r.data] } : old,
        );
        setTimeout(() => void qc.invalidateQueries({ queryKey: [`/offers/${offerId}/messages`] }), 800);
      },
    },
  });
  const list = q.data?.status === 200 ? q.data.data : [];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim()) post.mutate({ offerId, data: { text: text.trim() } });
  };
  return (
    <Panel title="Переписка">
      {list.length === 0 && !q.isPending && <p className="text-sm text-muted">Сообщений пока нет.</p>}
      <ul className="flex flex-col gap-2">
        {list.map((m) => (
          <li key={m.id} className={cn("max-w-[85%] rounded-xl px-3 py-2 text-sm", m.author_side === side ? "self-end bg-tint-50" : "self-start border border-hairline")}>
            <p className="whitespace-pre-wrap break-words">{m.text}</p>
            <p className="mt-1 text-[11px] text-muted">
              {m.author_side === side ? "Вы" : m.author_side === "company" ? "Компания" : "Кандидат"} · {dateTime(m.created_at)}
              {m.channel === "telegram" ? " · Telegram" : ""}
            </p>
          </li>
        ))}
      </ul>
      {canWrite ? (
        <form onSubmit={submit} className="flex flex-col gap-2">
          <label htmlFor="offer-msg" className="sr-only">Сообщение</label>
          <textarea id="offer-msg" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} rows={2} placeholder="Напишите сообщение" className={cn(fieldClass, "h-auto py-2")} />
          {post.isError && <ErrorNote>{offerErrorText(post.error)}</ErrorNote>}
          <Button type="submit" size="sm" className="self-end" disabled={post.isPending || !text.trim()}>
            Отправить
          </Button>
        </form>
      ) : (
        <p className="text-sm text-muted">Переписка закрыта.</p>
      )}
    </Panel>
  );
}

/** Сбросить все кеши, зависящие от приглашения: списки, карточки, переписку, историю. */
export function invalidateOffers(qc: ReturnType<typeof useQueryClient>) {
  const run = () =>
    qc.invalidateQueries({
      predicate: (q) => typeof q.queryKey[0] === "string" && (q.queryKey[0].startsWith("/offers") || q.queryKey[0].startsWith("/candidates/me/offers") || q.queryKey[0].startsWith("/candidates/me/interests")),
    });
  // Сервер коммитит после ответа: повторная сверка страхует от гонки с первым refetch.
  setTimeout(() => void run(), 800);
  return run();
}
