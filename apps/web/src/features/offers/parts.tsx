import { useQueryClient } from "@tanstack/react-query";

import { useListEventsOffersOfferIdEventsGet } from "@/api/endpoints/offers/offers";
import { buttonVariants, cn, SectionLabel } from "@fsp/ui";
import { ACTOR_LABEL, dateTime, OFFER_STATUS_LABEL, statusTone } from "./text";

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
    <Panel title="Статус">
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

export type ContactsData = { name?: string | null; email?: string | null; phone?: string | null; telegram?: string | null };

/** Ссылка на чат в Telegram по @нику (или готовой ссылке); без ника кнопки нет. */
export function telegramHref(handle: string | null | undefined): string | null {
  const h = (handle ?? "").trim();
  if (!h) return null;
  if (/^https?:\/\//.test(h)) return h;
  const nick = h.replace(/^@/, "");
  return /^[A-Za-z0-9_]{3,32}$/.test(nick) ? `https://t.me/${nick}` : null;
}

/** Контакты другой стороны: после принятия видны обеим сторонам; кнопка «Написать в Telegram». */
export function ContactsCard({ title, hint, contacts, testId }: { title: string; hint: string; contacts: ContactsData; testId?: string }) {
  const tg = telegramHref(contacts.telegram);
  return (
    <Panel title={title}>
      <div data-testid={testId} className="flex flex-col gap-3">
        <p className="text-xs text-muted">{hint}</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {contacts.name && (<><dt className="text-muted">Имя</dt><dd className="break-words">{contacts.name}</dd></>)}
          {contacts.email && (<><dt className="text-muted">Почта</dt><dd className="break-all"><a className="text-brand-fg" href={`mailto:${contacts.email}`}>{contacts.email}</a></dd></>)}
          {contacts.phone && (<><dt className="text-muted">Телефон</dt><dd><a className="text-brand-fg" href={`tel:${contacts.phone.replace(/[^+\d]/g, "")}`}>{contacts.phone}</a></dd></>)}
          {contacts.telegram && (<><dt className="text-muted">Telegram</dt><dd className="break-all">{contacts.telegram}</dd></>)}
        </dl>
        {tg && (
          <a href={tg} target="_blank" rel="noreferrer" className={cn(buttonVariants({ size: "lg" }), "w-full")}>
            Написать в Telegram
          </a>
        )}
      </div>
    </Panel>
  );
}

/** Одно сообщение стороны (сопроводительное или ответ): подпись и текст. */
export function MessageCard({ label, text, testId }: { label: string; text: string; testId?: string }) {
  return (
    <div data-testid={testId} className="flex flex-col gap-1">
      <SectionLabel>{label}</SectionLabel>
      <p className="whitespace-pre-wrap break-words rounded-lg bg-tint-50 p-3 text-sm">{text}</p>
    </div>
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
