import { PAGE } from "@/shared/lib/page";
import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { Avatar, Button, Dialog, DialogContent, DialogDescription, DialogTitle, ErrorState, Field, FieldInput, H1, Markdown, MarkdownEditor, Panel, PanelCap, ScrollTabs, Skeleton, StatusTag, Tabs, TabsContent, TabsTrigger, cn } from "@fsp/ui";
import {
  getGetMyCompanyCompaniesMeGetQueryKey,
  getAccessLogCompaniesMeAccessLogGetQueryKey,
  getMyTeamCompaniesMeMembersGetQueryKey,
  useAccessLogCompaniesMeAccessLogGet,
  useCreateHrCompaniesMeHrPost,
  useDeleteCompanyLogoCompaniesMeLogoDelete,
  useGetMyCompanyCompaniesMeGet,
  useMyTeamCompaniesMeMembersGet,
  usePatchMyCompanyCompaniesMePatch,
  usePutCompanyLogoCompaniesMeLogoPut,
  useRegisterCompanyCompaniesPost,
  useRemoveMemberCompaniesMeMembersUserIdDelete,
  useResetHrPasswordCompaniesMeMembersUserIdPasswordPost,
} from "@/api/endpoints/companies/companies";
import type { CompanyMemberOut, CompanyOut, HrAccessCard } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { ImagePicker } from "@/shared/ImagePicker";
import { useAuth } from "@/shared/lib/auth";
import { avatarSrc } from "@/shared/lib/avatar";
import { COMPANY as T, COMPANY_STATUS_HINT, COMPANY_STATUS_LABEL, vacancyErrorText } from "./text";

const errCode = (e: unknown) => (e instanceof ApiError ? e.code : undefined);

function StatusPanel({ status }: { status: string }) {
  return (
    <Panel aria-label={T.status} className="flex flex-col gap-1" data-testid="company-status">
      <p className="text-14 font-semibold">
        {T.status}:{" "}
        <span className={cn("rounded-md px-2 py-1 text-12", status === "verified" ? "bg-success-bg text-success" : status === "pending" ? "bg-warning-bg text-warning-fg" : "bg-error-bg text-error")}>
          {COMPANY_STATUS_LABEL[status] ?? status}
        </span>
      </p>
      <p className="text-14 text-muted">{COMPANY_STATUS_HINT[status] ?? ""}</p>
    </Panel>
  );
}

/** Форма компании: регистрация (нет компании) или правка владельцем. Описание — Markdown. */
function CompanyForm({ company, onDone }: { company: CompanyOut | null; onDone: () => void }) {
  const [name, setName] = useState("");
  const [inn, setInn] = useState("");
  const [site, setSite] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (company) {
      setName(company.name);
      setInn(company.inn ?? "");
      setSite(company.site ?? "");
      setDescription(company.description ?? "");
    }
  }, [company?.id, company?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = () => {
    setSaved(true);
    onDone();
  };
  const register = useRegisterCompanyCompaniesPost({ mutation: { onSuccess: done } });
  const patch = usePatchMyCompanyCompaniesMePatch({ mutation: { onSuccess: done } });
  const m = company ? patch : register;
  const nameError = name.trim().length < 2 ? T.nameError : undefined;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setSaved(false);
    if (nameError) return;
    const data = { name: name.trim(), inn: inn.trim() || null, site: site.trim() || null, description: description.trim() || null };
    if (company) patch.mutate({ data });
    else register.mutate({ data });
  };

  return (
    <Panel>
      <form onSubmit={submit} noValidate className="flex flex-col gap-4" data-testid="company-form">
        <Field label={`${T.name} *`} error={touched ? nameError : undefined}>
          <FieldInput value={name} onChange={(e) => setName(e.target.value)} maxLength={200} data-testid="company-name" />
        </Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={T.inn}>
            <FieldInput inputMode="numeric" value={inn} onChange={(e) => setInn(e.target.value)} maxLength={12} className="font-mono" data-testid="company-inn" />
          </Field>
          <Field label={T.site}>
            <FieldInput value={site} onChange={(e) => setSite(e.target.value)} maxLength={200} placeholder="https://" data-testid="company-site" />
          </Field>
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-14 font-medium">{T.about}</span>
          <MarkdownEditor value={description} onChange={setDescription} maxLength={5000} rows={8} aria-label={T.about} data-testid="company-description" />
          <span className="text-13 text-muted">{T.aboutHint}</span>
        </div>
        {m.isError && <ErrorNote>{vacancyErrorText(m.error)}</ErrorNote>}
        {saved && !m.isPending && (
          <p role="status" className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success">
            {T.saved}
          </p>
        )}
        <Button type="submit" size="lg" className="self-start" loading={m.isPending} data-testid="company-submit">
          {company ? T.save : T.register}
        </Button>
      </form>
    </Panel>
  );
}

/** Логотип компании: владелец загружает (`PUT|DELETE /companies/me/logo`), HR видит. Без файла — буквы на цвете. */
function LogoBlock({ company, owner, onChanged }: { company: CompanyOut; owner: boolean; onChanged: () => void }) {
  const put = usePutCompanyLogoCompaniesMeLogoPut();
  const del = useDeleteCompanyLogoCompaniesMeLogoDelete();
  if (!owner) {
    return (
      <Panel className="flex items-center gap-3" data-testid="company-logo">
        <Avatar name={company.name} src={avatarSrc(company.logo_url)} size={56} className="rounded-xl" />
        <span className="font-medium">{company.name}</span>
      </Panel>
    );
  }
  return (
    <Panel aria-label={T.logo.title}>
      <PanelCap title={T.logo.title} />
      <ImagePicker
        testId="company-logo"
        name={company.name}
        src={avatarSrc(company.logo_url)}
        size={72}
        text={T.logo}
        onUpload={async (file) => {
          await put.mutateAsync({ data: { file } });
          onChanged();
        }}
        onRemove={async () => {
          await del.mutateAsync();
          onChanged();
        }}
      />
    </Panel>
  );
}

/** Компания глазами HR: только чтение, описание отрисовано Markdown. */
function CompanyView({ company }: { company: CompanyOut }) {
  return (
    <Panel className="flex flex-col gap-3" data-testid="company-view">
      <p className="text-13 text-muted" data-testid="company-readonly">
        {T.readonly}
      </p>
      <div className="flex flex-col gap-1">
        <span className="text-13 text-muted">{T.name}</span>
        <span className="font-medium">{company.name}</span>
      </div>
      {(company.inn || company.site) && (
        <div className="grid gap-3 md:grid-cols-2">
          {company.inn && (
            <div className="flex flex-col gap-1">
              <span className="text-13 text-muted">{T.inn}</span>
              <span className="font-mono">{company.inn}</span>
            </div>
          )}
          {company.site && (
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-13 text-muted">{T.site}</span>
              <span className="break-words">{company.site}</span>
            </div>
          )}
        </div>
      )}
      <div className="flex flex-col gap-1">
        <span className="text-13 text-muted">{T.about}</span>
        {company.description ? <Markdown data-testid="company-description-view">{company.description}</Markdown> : <p className="text-14 text-muted">{T.aboutEmpty}</p>}
      </div>
    </Panel>
  );
}

function MemberRow({ m, canManage, onRemove, onReset, busy }: { m: CompanyMemberOut; canManage: boolean; onRemove: (m: CompanyMemberOut) => void; onReset: (m: CompanyMemberOut) => void; busy: "remove" | "reset" | null }) {
  const name = m.full_name || m.email || T.noName;
  const hr = canManage && m.role !== "admin";
  return (
    <li className="flex min-h-14 flex-wrap items-center gap-3 border-t border-hairline py-2.5 first:border-t-0" data-testid="company-member">
      <Avatar name={m.full_name || m.email} src={avatarSrc(m.avatar_url)} size={40} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">
          {name}
          {m.is_me && <span className="text-muted"> · {T.you}</span>}
        </span>
        <span className="truncate text-13 text-muted">{[m.position, m.full_name ? m.email : null].filter(Boolean).join(" · ")}</span>
        {hr && m.must_change_password && m.temp_password_expires_at && (
          <span className="text-13 text-muted" data-testid="company-member-pending">
            {T.hr.pending(dateTime(m.temp_password_expires_at))}
          </span>
        )}
      </div>
      <StatusTag state={m.role === "admin" ? "confirmed" : "claimed"}>{T.roles[m.role] ?? m.role}</StatusTag>
      {hr && (
        <div className="flex w-full flex-wrap gap-1 md:w-auto">
          {m.managed && (
            <Button variant="ghost" size="sm" loading={busy === "reset"} onClick={() => onReset(m)} data-testid="company-member-reset">
              {T.hr.reset}
            </Button>
          )}
          <Button variant="ghost" size="sm" loading={busy === "remove"} onClick={() => onRemove(m)} data-testid="company-member-remove">
            {T.hr.revoke}
          </Button>
        </div>
      )}
    </li>
  );
}

const dateTime = (iso: string) => new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

/** Карточка доступа HR: показывается владельцу один раз, пароль больше нигде не хранится. */
function AccessCard({ card, companyName, onClose }: { card: HrAccessCard; companyName: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const until = dateTime(card.expires_at);
  const text = T.hr.shareText({ company: companyName, url: card.login_url, login: card.email, password: card.temp_password, until });

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      /* буфер недоступен: данные видны и выделяются */
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      {/* Пароль виден один раз: случайный клик мимо окна его не закрывает */}
      <DialogContent
        role="alertdialog"
        aria-describedby="company-access-once"
        onInteractOutside={(e) => e.preventDefault()}
        className="flex max-h-[90dvh] flex-col gap-3 overflow-y-auto"
        data-testid="company-access-card"
      >
        <DialogTitle>{T.hr.cardTitle(card.full_name || card.email)}</DialogTitle>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-14">
          <dt className="text-muted">{T.hr.loginUrl}</dt>
          <dd className="break-all" data-testid="company-access-url">{card.login_url}</dd>
          <dt className="text-muted">{T.hr.login}</dt>
          <dd className="break-all" data-testid="company-access-login">{card.email}</dd>
          <dt className="text-muted">{T.hr.password}</dt>
          <dd className="break-all font-mono" data-testid="company-access-password">{card.temp_password}</dd>
          <dt className="text-muted">{T.hr.until}</dt>
          <dd>{until}</dd>
        </dl>
        <p id="company-access-once" className="rounded-md bg-warning-bg p-2 text-13 text-warning-fg" data-testid="company-access-once">
          {T.hr.once}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => void copy()} data-testid="company-access-copy">
            {copied ? T.copied : T.hr.copy}
          </Button>
          <Button type="button" variant="outline" onClick={onClose} data-testid="company-access-close">
            {T.hr.done}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Подтверждение выдачи нового пароля или отзыва доступа (вместо `window.confirm`). */
function ConfirmModal({ ask, onCancel, onConfirm }: { ask: { kind: "reset" | "remove"; m: CompanyMemberOut } | null; onCancel: () => void; onConfirm: () => void }) {
  const who = ask ? ask.m.full_name || ask.m.email || T.noName : "";
  return (
    <Dialog open={ask !== null} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent aria-describedby="company-confirm-text" data-testid="company-confirm">
        {ask && (
          <>
            <DialogTitle>{ask.kind === "reset" ? T.hr.resetTitle : T.hr.revokeTitle}</DialogTitle>
            <DialogDescription id="company-confirm-text">{ask.kind === "reset" ? T.hr.resetConfirm(who) : T.hr.revokeConfirm(who)}</DialogDescription>
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <Button type="button" variant="outline" onClick={onCancel} data-testid="company-confirm-cancel">
                {T.hr.cancel}
              </Button>
              <Button type="button" onClick={onConfirm} data-testid="company-confirm-ok">
                {ask.kind === "reset" ? T.hr.resetOk : T.hr.revokeOk}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Журнал доступа HR: кто, кого и когда добавил, сбросил пароль или отозвал (только владельцу). */
function AccessLog() {
  const q = useAccessLogCompaniesMeAccessLogGet({ query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : [];
  if (items.length === 0) return null;
  return (
    <details className="border-t border-hairline pt-3" data-testid="company-access-log">
      <summary className="min-h-11 cursor-pointer text-14 font-semibold">{T.hr.log}</summary>
      <ul className="flex flex-col">
        {items.map((e) => (
          <li key={e.id} className="flex flex-wrap gap-x-2 border-t border-hairline py-2 text-13 first:border-t-0" data-testid="company-access-log-item">
            <span className="text-muted">{dateTime(e.created_at)}</span>
            <span>{T.hr.logLine(e.action, e.actor_name || T.noName, e.target_name || e.target_email || T.noName)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Команда: участники (видят все); доступ HR — логин и временный пароль от владельца. */
function TeamPanel({ companyName }: { companyName: string }) {
  const qc = useQueryClient();
  const q = useMyTeamCompaniesMeMembersGet({ query: { retry: false } });
  const team = q.data?.status === 200 ? q.data.data : null;
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: getMyTeamCompaniesMeMembersGetQueryKey() });
    void qc.invalidateQueries({ queryKey: getAccessLogCompaniesMeAccessLogGetQueryKey() });
  };
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [card, setCard] = useState<HrAccessCard | null>(null);
  const [ask, setAsk] = useState<{ kind: "reset" | "remove"; m: CompanyMemberOut } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(T.actionError(errCode(e) ?? (e instanceof ApiError && e.status === 429 ? "rate_limited" : undefined)));
  const show = (res: { status: number; data: unknown }) => {
    if (res.status === 200 || res.status === 201) setCard(res.data as HrAccessCard);
    refresh();
  };
  const create = useCreateHrCompaniesMeHrPost({
    mutation: {
      onSuccess: (res) => {
        show(res);
        setEmail("");
        setName("");
      },
      onError: fail,
    },
  });
  const reset = useResetHrPasswordCompaniesMeMembersUserIdPasswordPost({ mutation: { onSuccess: show, onError: fail } });
  const remove = useRemoveMemberCompaniesMeMembersUserIdDelete({ mutation: { onSuccess: refresh, onError: fail } });
  const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
  const nameOk = name.trim().length >= 2;

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!emailOk || !nameOk) return;
    setError(null);
    setCard(null);
    create.mutate({ data: { email: email.trim(), full_name: name.trim() } });
  }

  const onReset = (m: CompanyMemberOut) => setAsk({ kind: "reset", m });
  const onRemove = (m: CompanyMemberOut) => setAsk({ kind: "remove", m });

  function confirmAsk() {
    if (!ask) return;
    const { kind, m } = ask;
    setAsk(null);
    setError(null);
    if (kind === "reset") {
      setCard(null);
      reset.mutate({ userId: m.user_id });
    } else remove.mutate({ userId: m.user_id });
  }

  const busyOf = (id: string) => (remove.isPending && remove.variables?.userId === id ? "remove" : reset.isPending && reset.variables?.userId === id ? "reset" : null);

  return (
    <Panel aria-label={T.team} data-testid="company-team">
      <PanelCap title={T.team} />
      <p className="mb-2 text-13 text-muted">{T.teamHint}</p>
      {q.isPending && <Skeleton className="h-28" />}
      {q.isError && <ErrorState title={T.teamError} onRetry={() => void q.refetch()} className="min-h-0 py-6" />}
      {team && (
        <div className="flex flex-col gap-4">
          <ul className="flex flex-col">
            {team.members.map((m) => (
              <MemberRow key={m.user_id} m={m} canManage={team.can_manage} onRemove={onRemove} onReset={onReset} busy={busyOf(m.user_id)} />
            ))}
          </ul>
          {card && <AccessCard card={card} companyName={companyName} onClose={() => setCard(null)} />}
          <ConfirmModal ask={ask} onCancel={() => setAsk(null)} onConfirm={confirmAsk} />
          {team.can_manage && (
            <form onSubmit={submit} noValidate className="flex flex-col gap-2 border-t border-hairline pt-4" data-testid="company-hr-form">
              <span className="text-14 font-semibold">{T.hr.title}</span>
              <p className="text-13 text-muted">{T.hr.hint}</p>
              <div className="flex flex-col gap-2 md:flex-row md:items-start">
                <Field label={T.hr.name} className="md:flex-1">
                  <FieldInput autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} placeholder="Анна Смирнова" data-testid="company-hr-name" />
                </Field>
                <Field label={T.hr.email} className="md:flex-1">
                  <FieldInput type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} placeholder="hr@company.ru" data-testid="company-hr-email" />
                </Field>
                <Button type="submit" className="md:mt-7" disabled={!emailOk || !nameOk} loading={create.isPending} data-testid="company-hr-submit">
                  {T.hr.submit}
                </Button>
              </div>
            </form>
          )}
          {error && (
            <p role="alert" className="text-13 text-error" data-testid="company-team-error">
              {error}
            </p>
          )}
          {team.can_manage && <AccessLog />}
          <Link to="/settings?tab=profile" className="text-14 font-medium text-brand-fg underline-offset-2 hover:underline">
            {T.profileLink}
          </Link>
        </div>
      )}
    </Panel>
  );
}

/** Компания работодателя: владелец правит и ведёт команду, HR видит компанию и команду. */
export default function Company() {
  const qc = useQueryClient();
  const { me, reloadMe } = useAuth();
  // Есть ли компания, известно из `GET /me`: без неё запрос дал бы 404 в консоли нового аккаунта.
  const hasCompany = !!me?.company;
  const q = useGetMyCompanyCompaniesMeGet({ query: { retry: false, enabled: hasCompany } });
  const company = q.data?.status === 200 ? q.data.data : null;
  const missing = !hasCompany || (q.error instanceof ApiError && q.error.status === 404);
  const owner = (company?.my_role ?? me?.company?.role) === "admin";

  const onDone = () => {
    void qc.invalidateQueries({ queryKey: getGetMyCompanyCompaniesMeGetQueryKey() });
    void reloadMe();
  };

  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "team" ? "team" : "info";

  return (
    <main className={PAGE.narrow} data-testid="company-page">
      <H1 className="text-[22px] leading-[1.2] md:text-[26px]">{T.title}</H1>
      {hasCompany && q.isPending && <Skeleton className="h-64" />}
      {q.isError && !missing && <ErrorState title={T.loadError} onRetry={() => void q.refetch()} />}
      {missing && (
        <>
          <Panel className="text-14">{T.missing}</Panel>
          <CompanyForm company={null} onDone={onDone} />
        </>
      )}
      {company && (
        <Tabs value={tab} onValueChange={(v) => setParams(v === "team" ? { tab: v } : {}, { replace: true })}>
          <ScrollTabs aria-label={T.title}>
            <TabsTrigger value="info" data-testid="company-tab-info">
              {T.tabs.info}
            </TabsTrigger>
            <TabsTrigger value="team" data-testid="company-tab-team">
              {T.tabs.team}
            </TabsTrigger>
          </ScrollTabs>
          <div className="flex flex-col gap-4 pt-4">
            <TabsContent value="info" className="flex flex-col gap-4">
              <StatusPanel status={company.status} />
              <LogoBlock company={company} owner={owner} onChanged={onDone} />
              {owner ? <CompanyForm company={company} onDone={onDone} /> : <CompanyView company={company} />}
              <Link to="/employer/tasks" className="inline-flex min-h-11 items-center self-start text-14 font-semibold text-brand-fg hover:underline">
                {T.tasks}
              </Link>
            </TabsContent>
            <TabsContent value="team">
              <TeamPanel companyName={company.name} />
            </TabsContent>
          </div>
        </Tabs>
      )}
    </main>
  );
}
