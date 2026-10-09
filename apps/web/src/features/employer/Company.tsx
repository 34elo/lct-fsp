import { PAGE } from "@/shared/lib/page";
import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Avatar, Button, ErrorState, Field, FieldInput, H1, Markdown, MarkdownEditor, Panel, PanelCap, Skeleton, StatusTag, cn } from "@fsp/ui";
import {
  getGetMyCompanyCompaniesMeGetQueryKey,
  getMyTeamCompaniesMeMembersGetQueryKey,
  useCreateInviteCompaniesMeInvitesPost,
  useGetMyCompanyCompaniesMeGet,
  useMyTeamCompaniesMeMembersGet,
  usePatchMyCompanyCompaniesMePatch,
  useRegisterCompanyCompaniesPost,
  useRemoveMemberCompaniesMeMembersUserIdDelete,
  useRevokeInviteCompaniesMeInvitesInviteIdDelete,
} from "@/api/endpoints/companies/companies";
import type { CompanyMemberOut, CompanyOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { dateOnly } from "@/features/offers/text";
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

function MemberRow({ m, canManage, onRemove, busy }: { m: CompanyMemberOut; canManage: boolean; onRemove: (m: CompanyMemberOut) => void; busy: boolean }) {
  const name = m.full_name || m.email || T.noName;
  return (
    <li className="flex min-h-14 items-center gap-3 border-t border-hairline py-2.5 first:border-t-0" data-testid="company-member">
      <Avatar name={m.full_name || m.email} src={avatarSrc(m.avatar_url)} size={40} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-medium">
          {name}
          {m.is_me && <span className="text-muted"> · {T.you}</span>}
        </span>
        <span className="truncate text-13 text-muted">{[m.position, m.full_name ? m.email : null].filter(Boolean).join(" · ")}</span>
      </div>
      <StatusTag state={m.role === "admin" ? "confirmed" : "claimed"}>{T.roles[m.role] ?? m.role}</StatusTag>
      {canManage && m.role !== "admin" && (
        <Button variant="ghost" size="sm" loading={busy} onClick={() => onRemove(m)} data-testid="company-member-remove">
          {T.remove}
        </Button>
      )}
    </li>
  );
}

/** Команда: участники (видят все), приглашения и управление — только владелец. */
function TeamPanel() {
  const qc = useQueryClient();
  const q = useMyTeamCompaniesMeMembersGet({ query: { retry: false } });
  const team = q.data?.status === 200 ? q.data.data : null;
  const refresh = () => void qc.invalidateQueries({ queryKey: getMyTeamCompaniesMeMembersGetQueryKey() });
  const [email, setEmail] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fail = (e: unknown) => setError(T.actionError(errCode(e)));
  const invite = useCreateInviteCompaniesMeInvitesPost({
    mutation: {
      onSuccess: (res) => {
        if (res.status === 201) setLink(res.data.url);
        setEmail("");
        refresh();
      },
      onError: fail,
    },
  });
  const revoke = useRevokeInviteCompaniesMeInvitesInviteIdDelete({ mutation: { onSuccess: refresh, onError: fail } });
  const remove = useRemoveMemberCompaniesMeMembersUserIdDelete({ mutation: { onSuccess: refresh, onError: fail } });
  const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!emailOk) return;
    setError(null);
    setLink(null);
    setCopied(false);
    invite.mutate({ data: { email: email.trim() } });
  }

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      /* буфер недоступен: ссылка видна и выделяется */
    }
  }

  function onRemove(m: CompanyMemberOut) {
    if (!window.confirm(T.removeConfirm(m.full_name || m.email || T.noName))) return;
    setError(null);
    remove.mutate({ userId: m.user_id });
  }

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
              <MemberRow key={m.user_id} m={m} canManage={team.can_manage} onRemove={onRemove} busy={remove.isPending && remove.variables?.userId === m.user_id} />
            ))}
          </ul>
          {team.can_manage && team.invites.length > 0 && (
            <div className="flex flex-col gap-1" data-testid="company-invites">
              <span className="text-13 font-semibold text-muted">{T.pending}</span>
              <ul className="flex flex-col">
                {team.invites.map((i) => (
                  <li key={i.id} className="flex min-h-11 flex-wrap items-center gap-2 border-t border-hairline py-2 first:border-t-0" data-testid="company-invite">
                    <span className="min-w-0 flex-1 truncate">{i.email}</span>
                    <span className="text-13 text-muted">{T.until(dateOnly(i.expires_at))}</span>
                    <Button variant="ghost" size="sm" loading={revoke.isPending && revoke.variables?.inviteId === i.id} onClick={() => revoke.mutate({ inviteId: i.id })} data-testid="company-invite-revoke">
                      {T.revoke}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {team.can_manage && (
            <form onSubmit={submit} noValidate className="flex flex-col gap-2 border-t border-hairline pt-4" data-testid="company-invite-form">
              <span className="text-14 font-semibold">{T.inviteTitle}</span>
              <div className="flex flex-col gap-2 md:flex-row md:items-start">
                <Field label={T.inviteEmail} hint={T.inviteHint} className="md:flex-1">
                  <FieldInput type="email" autoComplete="off" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={254} placeholder="hr@company.ru" data-testid="company-invite-email" />
                </Field>
                <Button type="submit" className="md:mt-7" disabled={!emailOk} loading={invite.isPending} data-testid="company-invite-submit">
                  {T.inviteSubmit}
                </Button>
              </div>
              {link && (
                <div role="status" className="flex flex-col gap-2 rounded-lg bg-tint-50 p-3" data-testid="company-invite-link">
                  <span className="text-13">{T.inviteCreated}</span>
                  <code className="break-all font-mono text-12">{link}</code>
                  <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => void copy()}>
                    {copied ? T.copied : T.copy}
                  </Button>
                </div>
              )}
            </form>
          )}
          {error && (
            <p role="alert" className="text-13 text-error" data-testid="company-team-error">
              {error}
            </p>
          )}
          <Link to="/settings?tab=profile" className="text-14 font-medium text-brand-fg underline-offset-2 hover:underline">
            {T.profileLink}
          </Link>
        </div>
      )}
    </Panel>
  );
}

/** Компания работодателя (E39-24): владелец правит и ведёт команду, HR видит компанию и команду. */
export default function Company() {
  const qc = useQueryClient();
  const { me, reloadMe } = useAuth();
  // Есть ли компания, известно из `GET /me`: без неё запрос дал бы 404 в консоли нового аккаунта (E39-7).
  const hasCompany = !!me?.company;
  const q = useGetMyCompanyCompaniesMeGet({ query: { retry: false, enabled: hasCompany } });
  const company = q.data?.status === 200 ? q.data.data : null;
  const missing = !hasCompany || (q.error instanceof ApiError && q.error.status === 404);
  const owner = (company?.my_role ?? me?.company?.role) === "admin";

  const onDone = () => {
    void qc.invalidateQueries({ queryKey: getGetMyCompanyCompaniesMeGetQueryKey() });
    void reloadMe();
  };

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
        <>
          <StatusPanel status={company.status} />
          {owner ? <CompanyForm company={company} onDone={onDone} /> : <CompanyView company={company} />}
          <TeamPanel />
          <Link to="/employer/tasks" className="inline-flex min-h-11 items-center self-start text-14 font-semibold text-brand-fg hover:underline">
            {T.tasks}
          </Link>
        </>
      )}
    </main>
  );
}
