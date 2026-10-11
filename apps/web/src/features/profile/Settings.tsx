import { PAGE } from "@/shared/lib/page";
import { Avatar, Button, EmptyState, ErrorState, Field, FieldInput, H1, MarkdownEditor, Panel, PanelCap, ScrollTabs, Skeleton, StatusTag, Tabs, TabsContent, TabsTrigger, buttonVariants } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { usePasswordChangeAuthPasswordChangePost } from "@/api/endpoints/auth/auth";
import {
  getGetProfileCandidatesMeProfileGetQueryKey,
  useDeleteAvatarCandidatesMeAvatarDelete,
  useGetProfileCandidatesMeProfileGet,
  usePutAvatarCandidatesMeAvatarPut,
  usePatchProfileCandidatesMeProfilePatch,
} from "@/api/endpoints/candidates/candidates";
import {
  getGetMyProfileMeProfileGetQueryKey,
  useDeleteMyAvatarMeAvatarDelete,
  useGetMyProfileMeProfileGet,
  usePatchMyProfileMeProfilePatch,
  usePutMyAvatarMeAvatarPut,
} from "@/api/endpoints/profile/profile";
import { ApiError } from "@/api/mutator";
import { getGetConsentsMeConsentsGetQueryKey, useGetConsentsMeConsentsGet, usePutConsentsMeConsentsPut } from "@/api/endpoints/consents/consents";
import { useMyLinkMeTelegramLinkPost } from "@/api/endpoints/telegram/telegram";
import type { ConsentOut } from "@/api/model";
import { authText } from "@/features/auth/text";
import { onboardingSkipped, setOnboardingSkipped } from "@/features/employer/match-model";
import { ImagePicker, type ImagePickerText } from "@/shared/ImagePicker";
import { useAuth, type Role } from "@/shared/lib/auth";
import { avatarSrc } from "@/shared/lib/avatar";
import { useTheme } from "@/shared/lib/theme";
import { PrivacySettings, SettingRow } from "./PrivacySettings";
import { SETTINGS as S } from "./text";

const copy = authText.consents.types as Record<string, { title: string; hint: string }>;

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

const PROFILE = S.profile;

/** Строка «аватар + почта + роль»: инициалы; фото — в блоке загрузки ниже. */
function AccountHead({ name }: { name?: string | null }) {
  const { me } = useAuth();
  return (
    <div className="flex items-center gap-3">
      <Avatar name={name || me?.email} size={56} />
      <div className="flex min-w-0 flex-col">
        <span className="truncate font-medium" data-testid="settings-account-email">
          {me?.email ?? PROFILE.account}
        </span>
        <span className="text-13 text-muted">{PROFILE.roles[me?.role ?? ""] ?? me?.role}</span>
      </div>
    </div>
  );
}

const SaveRow = ({ pending, saved, error, disabled }: { pending: boolean; saved: boolean; error: boolean; disabled?: boolean }) => (
  <div className="flex flex-wrap items-center gap-3">
    <Button type="submit" loading={pending} disabled={disabled}>
      {PROFILE.save}
    </Button>
    {saved && (
      <span role="status" className="text-13 text-muted" data-testid="settings-saved">
        {PROFILE.saved}
      </span>
    )}
    {error && (
      <span role="alert" className="text-13 text-error" data-testid="settings-save-error">
        {PROFILE.saveError}
      </span>
    )}
  </div>
);

type SaveState = "idle" | "saved" | "error";

/** ФИО кандидата: `PATCH /candidates/me/profile {full_name}`; пустое значение очищает. */
function CandidateProfileCard({ fullName, avatarUrl }: { fullName: string; avatarUrl?: string | null }) {
  const qc = useQueryClient();
  const { reloadMe } = useAuth();
  const patch = usePatchProfileCandidatesMeProfilePatch();
  const [value, setValue] = useState(fullName);
  const [state, setState] = useState<SaveState>("idle");
  const trimmed = value.trim();
  const invalid = trimmed.length > 120 ? PROFILE.nameTooLong : trimmed.length === 1 ? PROFILE.nameTooShort : undefined;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (invalid) return;
    setState("idle");
    try {
      const res = await patch.mutateAsync({ data: { full_name: trimmed || null } });
      if (res.status !== 200) throw new Error("profile");
      await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
      setState("saved");
    } catch {
      setState("error");
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-testid="settings-profile-form">
      <AccountHead name={trimmed} />
      <CandidateAvatarPicker
        name={trimmed}
        url={avatarUrl}
        onChanged={async () => {
          await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
          await reloadMe();
        }}
      />
      <Field label={PROFILE.fullName} hint={PROFILE.fullNameHint} error={invalid}>
        <FieldInput
          value={value}
          maxLength={130}
          autoComplete="name"
          onChange={(e) => {
            setValue(e.target.value);
            setState("idle");
          }}
          data-testid="settings-full-name"
        />
      </Field>
      <SaveRow pending={patch.isPending} saved={state === "saved"} error={state === "error"} disabled={!!invalid} />
    </form>
  );
}

const PHOTO_TEXT: ImagePickerText = {
  upload: PROFILE.photoUpload,
  replace: PROFILE.photoReplace,
  remove: PROFILE.photoRemove,
  hint: PROFILE.photoHint,
  error: PROFILE.photoError,
};

/** Фото сотрудника: `PUT|DELETE /me/avatar`; сервер проверяет сигнатуру файла. */
function AvatarPicker({ name, url, onChanged }: { name: string; url?: string | null; onChanged: () => Promise<void> }) {
  const put = usePutMyAvatarMeAvatarPut();
  const del = useDeleteMyAvatarMeAvatarDelete();
  return (
    <ImagePicker
      testId="settings-avatar"
      name={name}
      src={avatarSrc(url)}
      text={PHOTO_TEXT}
      onUpload={async (file) => {
        await put.mutateAsync({ data: { file } });
        await onChanged();
      }}
      onRemove={async () => {
        await del.mutateAsync();
        await onChanged();
      }}
    />
  );
}

/** Фото кандидата: `PUT|DELETE /candidates/me/avatar`. Работодатель видит его после приглашения. */
function CandidateAvatarPicker({ name, url, onChanged }: { name: string; url?: string | null; onChanged: () => Promise<void> }) {
  const put = usePutAvatarCandidatesMeAvatarPut();
  const del = useDeleteAvatarCandidatesMeAvatarDelete();
  return (
    <div className="flex flex-col gap-1">
      <ImagePicker
        testId="settings-avatar"
        name={name}
        src={avatarSrc(url)}
        text={{ ...PHOTO_TEXT, hint: `${PHOTO_TEXT.hint} ${PROFILE.photoCandidateHint}` }}
        onUpload={async (file) => {
          await put.mutateAsync({ data: { file } });
          await onChanged();
        }}
        onRemove={async () => {
          await del.mutateAsync();
          await onChanged();
        }}
      />
    </div>
  );
}

/** Строка «компания и роль в ней» для сотрудника; правка компании — на её странице (только владелец). */
function CompanyLine() {
  const { me } = useAuth();
  const company = me?.company;
  const [wizardHidden, setWizardHidden] = useState(() => onboardingSkipped());
  if (me?.role !== "employer") return null;
  return (
    <div className="flex flex-col gap-1 border-t border-hairline pt-4" data-testid="settings-company">
      <span className="text-13 text-muted">{PROFILE.companyLine}</span>
      {company ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{company.name}</span>
          <StatusTag state={company.role === "admin" ? "confirmed" : "claimed"} data-testid="settings-company-role">
            {PROFILE.companyRoles[company.role] ?? company.role}
          </StatusTag>
          <Link to="/employer/company" className="text-14 font-medium text-brand-fg underline-offset-2 hover:underline">
            {PROFILE.companyOpen}
          </Link>
        </div>
      ) : (
        <p className="text-14 text-muted" data-testid="settings-company-none">
          {PROFILE.companyNone}
        </p>
      )}
      {!company && wizardHidden && (
        <Button
          variant="outline"
          className="self-start"
          data-testid="settings-onboarding-show"
          onClick={() => {
            setOnboardingSkipped(false);
            setWizardHidden(false);
          }}
        >
          Показать вводный онбординг
        </Button>
      )}
    </div>
  );
}

/**
 * Личный профиль сотрудника компании и админа ФСП: ФИО, должность, фото, «О себе».
 * `GET|PATCH /me/profile`; имя, должность и фото подписывают приглашения кандидатам.
 */
function StaffProfileCard() {
  const qc = useQueryClient();
  const q = useGetMyProfileMeProfileGet({ query: { retry: false } });
  const patch = usePatchMyProfileMeProfilePatch();
  const data = q.data?.status === 200 ? q.data.data : null;
  const [form, setForm] = useState({ full_name: "", position: "", about: "" });
  const [loaded, setLoaded] = useState(false);
  const [state, setState] = useState<SaveState>("idle");
  if (data && !loaded) {
    setLoaded(true);
    setForm({ full_name: data.full_name ?? "", position: data.position ?? "", about: data.about ?? "" });
  }
  const name = form.full_name.trim();
  const invalid = name.length > 120 ? PROFILE.nameTooLong : name.length === 1 ? PROFILE.nameTooShort : undefined;
  const set = (k: keyof typeof form) => (v: string) => {
    setForm((f) => ({ ...f, [k]: v }));
    setState("idle");
  };
  const { reloadMe } = useAuth();
  const refresh = async () => {
    await qc.invalidateQueries({ queryKey: getGetMyProfileMeProfileGetQueryKey() });
    await reloadMe();
  };

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (invalid) return;
    setState("idle");
    try {
      await patch.mutateAsync({ data: { full_name: name || null, position: form.position.trim() || null, about: form.about.trim() || null } });
      await refresh();
      setState("saved");
    } catch {
      setState("error");
    }
  }

  if (q.isPending) return <Skeleton className="h-64" />;
  if (!data) return <LoadError onRetry={() => void q.refetch()} status={q.error?.status} />;
  return (
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4" data-testid="settings-profile-form">
      <AccountHead name={name} />
      <p className="text-13 text-muted">{PROFILE.staffHint}</p>
      <AvatarPicker name={name} url={data.avatar_url} onChanged={refresh} />
      <div className="grid gap-4 md:grid-cols-2">
        <Field label={PROFILE.fullName} error={invalid}>
          <FieldInput value={form.full_name} maxLength={130} autoComplete="name" onChange={(e) => set("full_name")(e.target.value)} data-testid="settings-full-name" />
        </Field>
        <Field label={PROFILE.position}>
          <FieldInput value={form.position} maxLength={120} placeholder={PROFILE.positionPlaceholder} autoComplete="organization-title" onChange={(e) => set("position")(e.target.value)} data-testid="settings-position" />
        </Field>
      </div>
      <Field label={PROFILE.about} hint={PROFILE.aboutHint}>
        <MarkdownEditor value={form.about} onChange={set("about")} maxLength={2000} rows={5} aria-label={PROFILE.about} data-testid="settings-about" />
      </Field>
      <SaveRow pending={patch.isPending} saved={state === "saved"} error={state === "error"} disabled={!!invalid} />
      <CompanyLine />
    </form>
  );
}

function ConsentEmpty() {
  return (
    <EmptyState
      className="min-h-[200px]"
      title={S.empty}
      action={
        <Link to="/consents" className={buttonVariants({ size: "lg" })} data-testid="settings-empty-action">
          {S.emptyAction}
        </Link>
      }
    />
  );
}

function LoadError({ onRetry, status }: { onRetry: () => void; status?: number }) {
  return (
    <div className="w-full" data-testid="settings-error-state">
      <ErrorState title={S.loadError} code={status ? S.errorCode(status) : undefined} onRetry={onRetry} />
    </div>
  );
}

/** Профиль: кандидат правит ФИО анкеты, сотрудник компании и админ — личный профиль. */
function ProfileTab({ role }: { role: Role }) {
  const pq = useGetProfileCandidatesMeProfileGet({ query: { retry: false, enabled: role === "candidate" } });
  let body: ReactNode;
  if (role !== "candidate") body = <StaffProfileCard />;
  else if (pq.isPending) body = <Skeleton className="h-40" />;
  else if (pq.data?.status === 403) body = <ConsentEmpty />;
  else if (pq.data?.status !== 200) body = <LoadError onRetry={() => void pq.refetch()} status={pq.error?.status} />;
  else body = <CandidateProfileCard fullName={pq.data.data.full_name ?? ""} avatarUrl={pq.data.data.avatar_url} />;
  return (
    <Panel data-testid="settings-profile" aria-label={PROFILE.title}>
      <PanelCap title={PROFILE.title} />
      {body}
    </Panel>
  );
}

/** Приватность кандидата: профиль нужен для текущих значений переключателей. */
function PrivacyTab() {
  const pq = useGetProfileCandidatesMeProfileGet({ query: { retry: false } });
  if (pq.isPending) return <Skeleton className="h-64" />;
  if (pq.data?.status === 403) return <ConsentEmpty />;
  if (pq.data?.status !== 200) return <LoadError onRetry={() => void pq.refetch()} status={pq.error?.status} />;
  return (
    <div>
      <PrivacySettings visibility={pq.data.data.visibility} />
    </div>
  );
}

/** Вкладки со списком согласий: общий запрос, пустое состояние и ошибка. */
function ConsentsTab({ role, view }: { role: Role; view: "notifications" | "consents" }) {
  const cq = useGetConsentsMeConsentsGet({ query: { retry: false } });
  if (cq.isPending) return <Skeleton className="h-48" />;
  const items = cq.data?.status === 200 ? (cq.data.data as ConsentOut[]) : null;
  if (!items) return <LoadError onRetry={() => void cq.refetch()} status={cq.error?.status} />;
  if (role === "candidate" && !items.find((c) => c.type === "pd_processing")?.granted) return <ConsentEmpty />;
  const telegram = items.find((c) => c.type === "telegram_notifications");
  // Работодателю нужны согласие на ПДн и Telegram: остальные типы относятся к анкете кандидата.
  const rest = items.filter((c) => c.type !== "telegram_notifications" && c.type !== "code_analysis" && (role === "candidate" || c.type === "pd_processing"));
  return <div>{view === "notifications" ? <NotificationsCard consent={telegram} /> : <ConsentsCard items={rest} />}</div>;
}

/** Смена пароля: `POST /auth/password/change`. Без пароля (вход через Telegram) — пояснение вместо формы. */
function SecurityTab() {
  const { me } = useAuth();
  const change = usePasswordChangeAuthPasswordChangePost();
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const T = S.security;

  if (!me?.email)
    return (
      <Panel data-testid="settings-security">
        <PanelCap title={T.title} />
        <p className="text-14 text-muted">{T.noPassword}</p>
      </Panel>
    );

  const errors = {
    next: next && next.length < 8 ? T.min : next && next === cur ? T.same : undefined,
    again: again && again !== next ? T.mismatch : undefined,
  };
  const ready = cur !== "" && next.length >= 8 && again === next && next !== cur;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    setMsg(null);
    try {
      await change.mutateAsync({ data: { current_password: cur, new_password: next } });
      setCur("");
      setNext("");
      setAgain("");
      setMsg({ ok: true, text: T.done });
    } catch (err) {
      const api = err instanceof ApiError ? err : null;
      setMsg({ ok: false, text: api?.code === "wrong_password" ? T.wrong : api?.status === 429 ? T.limit : T.error });
    }
  }

  return (
    <Panel data-testid="settings-security" aria-label={T.title}>
      <PanelCap title={T.title} />
      <p className="mb-3 text-13 text-muted">{T.hint}</p>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
        <Field label={T.current}>
          <FieldInput type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} data-testid="settings-password-current" />
        </Field>
        <Field label={T.next} error={errors.next}>
          <FieldInput type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} data-testid="settings-password-new" />
        </Field>
        <Field label={T.repeat} error={errors.again}>
          <FieldInput type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} data-testid="settings-password-repeat" />
        </Field>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={change.isPending} disabled={!ready} data-testid="settings-password-submit">
            {T.submit}
          </Button>
          {msg && (
            <span role={msg.ok ? "status" : "alert"} className={msg.ok ? "text-13 text-muted" : "text-13 text-error"} data-testid="settings-password-message">
              {msg.text}
            </span>
          )}
        </div>
      </form>
    </Panel>
  );
}

type TabId = keyof typeof S.tabs;

/** Вкладки по роли: нет вкладки — нет данных или API для роли (приватность и согласия анкеты). */
export function tabsFor(role: Role | null): TabId[] {
  if (role === "candidate") return ["profile", "privacy", "notifications", "consents", "appearance", "security"];
  if (role === "employer") return ["profile", "notifications", "consents", "appearance", "security"];
  return ["profile", "appearance", "security"];
}

/**
 * Настройки `/settings` для всех ролей: Профиль, Приватность (кандидат), Уведомления,
 * Согласия, Оформление, Безопасность. Вкладка — в `?tab=`, на 375 px полоса листается пальцем.
 * Сотрудник компании и админ загружают фото, у кандидата — инициалы.
 */
export default function Settings() {
  const { role } = useAuth();
  const [params, setParams] = useSearchParams();
  const tabs = tabsFor(role);
  const asked = params.get("tab") ?? "";
  const tab = (tabs as string[]).includes(asked) ? (asked as TabId) : tabs[0]!;

  return (
    <div className={PAGE.normal} data-testid="settings-page">
      <H1 className="text-[22px] leading-[1.2] md:text-[26px]">{S.title}</H1>
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })}>
        <ScrollTabs aria-label={S.tabsLabel}>
          {tabs.map((t) => (
            <TabsTrigger key={t} value={t} data-testid={`settings-tab-${t}`}>
              {S.tabs[t]}
            </TabsTrigger>
          ))}
        </ScrollTabs>
        {role && (
          <div className="pt-4">
            <TabsContent value="profile">
              <ProfileTab role={role} />
            </TabsContent>
            <TabsContent value="privacy">
              <PrivacyTab />
            </TabsContent>
            <TabsContent value="notifications">
              <ConsentsTab role={role} view="notifications" />
            </TabsContent>
            <TabsContent value="consents">
              <ConsentsTab role={role} view="consents" />
            </TabsContent>
            <TabsContent value="appearance">
              <div>
                <AppearanceCard />
              </div>
            </TabsContent>
            <TabsContent value="security">
              <SecurityTab />
            </TabsContent>
          </div>
        )}
      </Tabs>
    </div>
  );
}
