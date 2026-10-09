import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ChangeEvent } from "react";

import {
  getFspMyRequestCandidatesMeFspRequestGetQueryKey,
  getFspOverviewCandidatesMeFspGetQueryKey,
  useFspCreateRequestCandidatesMeFspRequestsPost,
  useFspMyRequestCandidatesMeFspRequestGet,
  useFspOverviewCandidatesMeFspGet,
  useFspRegistryLinkCandidatesMeFspRegistryLinkPost,
  useFspSyncCandidatesMeFspSyncPost,
} from "@/api/endpoints/fsp/fsp";
import type { FspRequestOut, RegistryLinkOut } from "@/api/model";
import { Button, Field, FieldInput } from "@fsp/ui";
import { ErrorNote } from "@/features/auth/ui";
import { FSP, fspApiError } from "@/features/fsp/text";

/** Сколько ждём первые достижения после привязки (fsp.linked → fsp.sync → импорт в core). */
const IMPORT_WAIT_MS = 30_000;

type Draft = { full_name: string; email: string; phone: string; event: string };
const EMPTY: Draft = { full_name: "", email: "", phone: "", event: "" };

/**
 * Привязка ФСП через реестр (E39-28, ADR-052): одна кнопка «Привязать ФСП» ищет email аккаунта и
 * телефон из профиля в реестре; совпало — привязка сразу, иначе заявка админу ФСП.
 * OAuth «Войти через ФСП» и ввод кода в UI больше нет (бэкенд сохранён).
 */
export function FspLinkPanel({ onLinked }: { onLinked?: () => void }) {
  const qc = useQueryClient();
  const [waitUntil, setWaitUntil] = useState<number | null>(null);
  const overview = useFspOverviewCandidatesMeFspGet({
    query: { refetchInterval: waitUntil ? 2000 : false },
  });
  const myRequest = useFspMyRequestCandidatesMeFspRequestGet({ query: { retry: false } });
  const registryLink = useFspRegistryLinkCandidatesMeFspRegistryLinkPost();
  const createRequest = useFspCreateRequestCandidatesMeFspRequestsPost();
  const sync = useFspSyncCandidatesMeFspSyncPost();

  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [form, setForm] = useState<Draft | null>(null);
  const [notFound, setNotFound] = useState(false);

  const ov = overview.data?.status === 200 ? overview.data.data : undefined;
  const linked = ov?.link.linked ?? false;
  const verified = ov?.link.verified ?? false;
  const teams = ov?.teams ?? [];
  const achievements = ov?.achievements.length ?? 0;
  const req: FspRequestOut | null = myRequest.data?.status === 200 ? (myRequest.data.data ?? null) : null;

  // Ждём импорт достижений: появились — обновляем все экраны (Главная, профиль), время вышло — перестаём опрашивать.
  useEffect(() => {
    if (!waitUntil) return;
    if (linked && achievements > 0) {
      setWaitUntil(null);
      setInfo(FSP.imported);
      void qc.invalidateQueries();
      return;
    }
    const t = window.setTimeout(() => {
      setWaitUntil(null);
      void qc.invalidateQueries();
    }, Math.max(0, waitUntil - Date.now()));
    return () => window.clearTimeout(t);
  }, [waitUntil, linked, achievements, qc]);

  async function link() {
    setError(null);
    setInfo(null);
    try {
      const res = await registryLink.mutateAsync();
      const out = res.data as RegistryLinkOut;
      if (out.linked) {
        setNotFound(false);
        setInfo(`${FSP.found(out.matched_by)} ${FSP.importing}`);
        setWaitUntil(Date.now() + IMPORT_WAIT_MS);
        await qc.invalidateQueries({ queryKey: getFspOverviewCandidatesMeFspGetQueryKey() });
        onLinked?.();
      } else {
        setNotFound(true);
        setForm({ ...EMPTY, ...(req ? fromRequest(req) : {}) });
      }
    } catch (e) {
      setError(fspApiError(e));
    }
  }

  async function sendRequest(d: Draft) {
    setError(null);
    try {
      await createRequest.mutateAsync({
        data: {
          full_name: d.full_name.trim(),
          email: d.email.trim() || null,
          phone: d.phone.trim() || null,
          event: d.event.trim() || null,
        },
      });
      setForm(null);
      setNotFound(false);
      await qc.invalidateQueries({ queryKey: getFspMyRequestCandidatesMeFspRequestGetQueryKey() });
    } catch (e) {
      setError(fspApiError(e));
    }
  }

  async function runSync() {
    setError(null);
    try {
      await sync.mutateAsync();
      setInfo(FSP.syncing);
    } catch (e) {
      setError(fspApiError(e));
    }
  }

  const notes = (
    <>
      {error && <ErrorNote>{error}</ErrorNote>}
      {info && (
        <p role="status" className="text-sm text-brand-fg">
          {info}
        </p>
      )}
    </>
  );

  if (overview.isPending) return <p role="status" className="text-sm text-muted">{FSP.checking}</p>;

  if (linked) {
    return (
      <div className="flex flex-col gap-2" data-testid="fsp-linked">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold">{verified ? FSP.linked : FSP.linkedManual}</span>
          {ov?.link.participant_id && <span className="font-mono text-xs text-muted">{ov.link.participant_id}</span>}
          {teams.length > 0 && (
            <span className="text-xs text-muted">
              {FSP.teams} {teams.map((t) => t.name).join(", ")}
            </span>
          )}
        </p>
        {notes}
        <Button variant="outline" size="sm" className="self-start" onClick={() => void runSync()} disabled={sync.isPending}>
          {FSP.sync}
        </Button>
      </div>
    );
  }

  if (form) {
    const valid = form.full_name.trim().length >= 2 && Boolean(form.email.trim() || form.phone.trim());
    const set = (k: keyof Draft) => (e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
    return (
      <form
        className="flex flex-col gap-3"
        aria-label={FSP.formTitle}
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) void sendRequest(form);
        }}
      >
        {notFound && <p className="text-sm">{FSP.notFound}</p>}
        {notes}
        <Field label={FSP.fullName}>
          <FieldInput value={form.full_name} onChange={set("full_name")} autoComplete="name" maxLength={200} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={FSP.email} hint={FSP.contactHint}>
            <FieldInput type="email" value={form.email} onChange={set("email")} autoComplete="email" maxLength={254} />
          </Field>
          <Field label={FSP.phone}>
            <FieldInput type="tel" value={form.phone} onChange={set("phone")} autoComplete="tel" maxLength={32} />
          </Field>
        </div>
        <Field label={FSP.event} hint={FSP.eventHint}>
          <FieldInput value={form.event} onChange={set("event")} maxLength={200} />
        </Field>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" disabled={!valid || createRequest.isPending}>
            {createRequest.isPending ? FSP.sending : FSP.send}
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => setForm(null)}>
            {FSP.cancel}
          </Button>
        </div>
      </form>
    );
  }

  if (req?.status === "pending") {
    return (
      <div className="flex flex-col gap-2" data-testid="fsp-request-pending">
        <p className="text-sm">
          <span className="font-semibold">{FSP.since(req.created_at)}.</span> {FSP.pending}
        </p>
        {notes}
        <Button variant="outline" size="sm" className="self-start" onClick={() => setForm(fromRequest(req))}>
          {FSP.pendingEdit}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {req?.status === "rejected" && (
        <div className="rounded-lg border border-hairline px-3 py-2 text-sm" data-testid="fsp-request-rejected">
          <span className="font-semibold">{FSP.rejected}</span>
          {req.reason ? `: ${req.reason}` : ""}
        </div>
      )}
      {notes}
      <Button size="lg" className="self-start" onClick={() => void link()} disabled={registryLink.isPending}>
        {registryLink.isPending ? FSP.linking : FSP.linkBtn}
      </Button>
      <p className="text-[13px] text-muted">{FSP.linkHint}</p>
      {req?.status === "rejected" && (
        <button type="button" className="self-start text-sm text-brand-fg underline" onClick={() => setForm(fromRequest(req))}>
          {FSP.retry}
        </button>
      )}
    </div>
  );
}

function fromRequest(r: FspRequestOut): Draft {
  return { full_name: r.full_name, email: r.email ?? "", phone: r.phone ?? "", event: r.event ?? "" };
}
