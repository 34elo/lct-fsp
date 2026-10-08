import { PAGE } from "@/shared/lib/page";
import { Button, EmptyState, ErrorState, H1, Panel, PanelCap, Skeleton, StatusTag, buttonVariants } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { useGetProfileCandidatesMeProfileGet } from "@/api/endpoints/candidates/candidates";
import { getGetConsentsMeConsentsGetQueryKey, useGetConsentsMeConsentsGet, usePutConsentsMeConsentsPut } from "@/api/endpoints/consents/consents";
import { useMyLinkMeTelegramLinkPost } from "@/api/endpoints/telegram/telegram";
import type { ConsentOut } from "@/api/model";
import { authText } from "@/features/auth/text";
import { useAuth } from "@/shared/lib/auth";
import { useTheme } from "@/shared/lib/theme";
import { PrivacySettings, SettingRow } from "./PrivacySettings";
import { SETTINGS as S } from "./text";

const copy = authText.consents.types as Record<string, { title: string; hint: string }>;

function SettingsSkeleton() {
  return (
    <div className="flex flex-col gap-3" data-testid="settings-loading">
      <p role="status" className="sr-only">
        {S.loading}
      </p>
      <Skeleton className="h-7 w-[220px]" />
      <div className="grid gap-4 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-36" />
        ))}
      </div>
    </div>
  );
}

/** Выдача и отзыв одного согласия: `PUT /me/consents` с текущей версией текста. */
function useConsentToggle(onError: (msg: string) => void) {
  const qc = useQueryClient();
  const save = usePutConsentsMeConsentsPut();
  async function toggle(c: ConsentOut, granted: boolean) {
    try {
      const res = await save.mutateAsync({ data: { consents: [{ type: c.type, granted, version: c.current_version }] } });
      if (res.status !== 200) throw new Error("consents");
    } catch {
      onError(S.consentError);
    }
    await qc.invalidateQueries({ queryKey: getGetConsentsMeConsentsGetQueryKey() });
  }
  return { toggle, pending: save.isPending };
}

const ErrorLine = ({ id, children }: { id: string; children: ReactNode }) => (
  <p role="alert" className="mt-2 rounded-lg bg-tint-50 px-3 py-2 text-13" data-testid={id}>
    {children}
  </p>
);

/** Согласия (кроме Telegram — он в «Уведомлениях»). Обязательные видны включёнными и не отзываются. */
function ConsentsCard({ items }: { items: ConsentOut[] }) {
  const [error, setError] = useState<string | null>(null);
  const { toggle, pending } = useConsentToggle(setError);
  return (
    <Panel data-testid="settings-consents" aria-label={S.consents}>
      <PanelCap title={S.consents} />
      <p className="mb-2 text-13 text-muted">{S.consentsHint}</p>
      {items.map((c) => (
        <SettingRow
          key={c.type}
          id={`consent-${c.type}`}
          label={copy[c.type]?.title ?? c.type}
          hint={copy[c.type]?.hint}
          checked={c.granted}
          disabled={c.required || pending}
          onChange={(v) => {
            setError(null);
            void toggle(c, v);
          }}
          testId={`settings-consent-${c.type}`}
        />
      ))}
      {error && <ErrorLine id="settings-consent-error">{error}</ErrorLine>}
    </Panel>
  );
}

/** Уведомления: согласие на Telegram и привязка бота (`POST /me/telegram/link`). */
function NotificationsCard({ consent }: { consent?: ConsentOut }) {
  const { me } = useAuth();
  const link = useMyLinkMeTelegramLinkPost();
  const [error, setError] = useState<string | null>(null);
  const { toggle, pending } = useConsentToggle(setError);

  async function openLink() {
    setError(null);
    try {
      const res = await link.mutateAsync();
      if (res.status !== 200) throw new Error("link");
      window.open(res.data.deep_link, "_blank", "noopener,noreferrer");
    } catch {
      setError(S.telegramLinkError);
    }
  }

  return (
    <Panel data-testid="settings-notifications" aria-label={S.notifications}>
      <PanelCap title={S.notifications} />
      {consent && (
        <SettingRow
          id="consent-telegram_notifications"
          label={copy.telegram_notifications?.title ?? S.telegram}
          hint={copy.telegram_notifications?.hint}
          checked={consent.granted}
          disabled={pending}
          onChange={(v) => {
            setError(null);
            void toggle(consent, v);
          }}
          testId="settings-consent-telegram_notifications"
        />
      )}
      <div className="flex min-h-11 items-center gap-3 border-t border-hairline py-2.5">
        <span className="flex-1 font-medium">{S.telegram}</span>
        {me?.telegram_linked ? (
          <StatusTag state="confirmed" data-testid="settings-telegram-linked">
            {S.telegramLinked}
          </StatusTag>
        ) : (
          <Button variant="outline" loading={link.isPending} onClick={() => void openLink()} data-testid="settings-telegram-link">
            {S.telegramLink}
          </Button>
        )}
      </div>
      {error && <ErrorLine id="settings-error">{error}</ErrorLine>}
    </Panel>
  );
}

/** Тема: светлая или тёмная (режима «системная» нет: до первого выбора тема следует системной). */
function AppearanceCard() {
  const { mode, setMode } = useTheme();
  const opts = [
    { v: "light", label: S.themeLight },
    { v: "dark", label: S.themeDark },
  ] as const;
  return (
    <Panel data-testid="settings-appearance" aria-label={S.appearance}>
      <PanelCap title={S.appearance} />
      <p className="mb-2 text-13 text-muted">{S.appearanceHint}</p>
      <div role="group" aria-label={S.themeLabel} className="flex gap-2">
        {opts.map((o) => (
          <Button key={o.v} variant={mode === o.v ? "default" : "outline"} aria-pressed={mode === o.v} onClick={() => setMode(o.v)} data-testid={`settings-theme-${o.v}`}>
            {o.label}
          </Button>
        ))}
      </div>
    </Panel>
  );
}

/**
 * Настройки кандидата `/me/settings` (E38-7, макеты v2_me-settings__*, бриф §6.8): «Что видят компании»,
 * согласия и уведомления. Переключатели применяются сразу. Нет `pd_processing` — пустое состояние.
 */
export default function Settings() {
  const pq = useGetProfileCandidatesMeProfileGet({ query: { retry: false } });
  const cq = useGetConsentsMeConsentsGet({ query: { retry: false } });

  const page = (body: ReactNode, title = true) => (
    <div className={PAGE.normal} data-testid="settings-page">
      {title && <H1 className="text-[22px] leading-[1.2] md:text-[26px]">{S.title}</H1>}
      {body}
    </div>
  );

  if (pq.isPending || cq.isPending) return page(<SettingsSkeleton />, false);
  const items = cq.data?.status === 200 ? (cq.data.data as ConsentOut[]) : null;
  const noConsent = pq.data?.status === 403 || (items !== null && !items.find((c) => c.type === "pd_processing")?.granted);
  if (items && noConsent)
    return page(
      <EmptyState
        className="min-h-[200px]"
        title={S.empty}
        action={
          <Link to="/consents" className={buttonVariants({ size: "lg" })} data-testid="settings-empty-action">
            {S.emptyAction}
          </Link>
        }
      />,
    );
  if (!items || pq.data?.status !== 200) {
    const status = (pq.error ?? cq.error)?.status;
    return page(
      <div className="w-full max-w-2xl" data-testid="settings-error-state">
        <ErrorState
          title={S.loadError}
          code={status ? S.errorCode(status) : undefined}
          onRetry={() => {
            void pq.refetch();
            void cq.refetch();
          }}
        />
      </div>,
    );
  }

  return page(
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-2 lg:items-start" data-testid="settings-main">
      <PrivacySettings visibility={pq.data.data.visibility} />
      <div className="flex flex-col gap-4">
        <AppearanceCard />
        <ConsentsCard items={items.filter((c) => c.type !== "telegram_notifications")} />
        <NotificationsCard consent={items.find((c) => c.type === "telegram_notifications")} />
      </div>
    </div>,
  );
}
