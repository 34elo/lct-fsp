import { useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent, type ComponentProps, type FormEvent } from "react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  Combobox,
  EmptyState,
  ErrorState,
  Field,
  FieldInput,
  NumberInput,
  Select,
  Skeleton,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Textarea,
  useFieldProps,
  type ComboOption,
  type OptionSource,
} from "@fsp/ui";

import {
  registryParticipantsAdminFspParticipantsGet,
  useRegistryAcceptRequestAdminFspRequestsRequestIdAcceptPost,
  useRegistryCreateEventAdminFspEventsPost,
  useRegistryCreateParticipantAdminFspParticipantsPost,
  useRegistryDeleteResultAdminFspResultsResultIdDelete,
  useRegistryEventsAdminFspEventsGet,
  useRegistryImportParticipantsAdminFspParticipantsImportPost,
  useRegistryParticipantsAdminFspParticipantsGet,
  useRegistryRejectRequestAdminFspRequestsRequestIdRejectPost,
  useRegistryRequestsAdminFspRequestsGet,
  useRegistryResultsAdminFspResultsGet,
  useRegistryUpdateEventAdminFspEventsEventIdPatch,
  useRegistryUpsertResultAdminFspResultsPut,
} from "@/api/endpoints/admin/admin";
import type {
  AdminFspRequestOut,
  CsvImportOut,
  FspDiscipline,
  FspLevel,
  RegistryEventOut,
  RegistryParticipantOut,
} from "@/api/model";
import { ApiError } from "@/api/mutator";
import { AdminPageHeader } from "@/features/admin/PageHeader";
import { PAGE } from "@/shared/lib/page";

import { DISCIPLINE, LEVEL, R } from "./text";

type Tab = "events" | "participants" | "results";
type ReqStatus = "pending" | "accepted" | "rejected";

const DISCIPLINE_OPTIONS: ComboOption[] = Object.entries(DISCIPLINE).map(([value, label]) => ({ value, label }));
const LEVEL_OPTIONS: ComboOption[] = Object.entries(LEVEL).map(([value, label]) => ({ value, label }));

/** Все запросы раздела начинаются с `/admin/fsp/` — после правки обновляем их разом. */
function useRefresh() {
  const qc = useQueryClient();
  return () =>
    qc.invalidateQueries({
      predicate: (q) => typeof q.queryKey[0] === "string" && q.queryKey[0].startsWith("/admin/fsp/"),
    });
}

/** Textarea, связанная с подписью `Field` (id и aria). */
function FieldTextarea(p: ComponentProps<typeof Textarea>) {
  return <Textarea {...useFieldProps()} {...p} />;
}

function ErrorLine({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <p role="alert" className="text-14 text-error">
      {text}
    </p>
  );
}

const errText = (e: unknown) => (e instanceof ApiError && e.code === "participant_exists" ? R.pt.exists : R.error);

/** Поиск участников реестра для комбобоксов. */
const participantSource: OptionSource = async (query, signal) => {
  const res = await registryParticipantsAdminFspParticipantsGet({ q: query || undefined, limit: 20 }, { signal });
  const items = res.status === 200 ? res.data : [];
  return items.map(participantOption);
};

function participantOption(p: RegistryParticipantOut): ComboOption {
  return { value: p.id, label: p.full_name, hint: [p.email, p.phone, p.id].filter(Boolean).join(" · ") };
}

// ---------------------------------------------------------------------------------- мероприятия
type EventDraft = { id: string | null; title: string; discipline: string | null; level: string | null; date: string };
const NEW_EVENT: EventDraft = { id: null, title: "", discipline: null, level: null, date: "" };

function Events({ onResults }: { onResults: (eventId: string) => void }) {
  const refresh = useRefresh();
  const q = useRegistryEventsAdminFspEventsGet({ query: { retry: false } });
  const create = useRegistryCreateEventAdminFspEventsPost();
  const update = useRegistryUpdateEventAdminFspEventsEventIdPatch();
  const [draft, setDraft] = useState<EventDraft>(NEW_EVENT);
  const [err, setErr] = useState<string | null>(null);
  const items = q.data?.status === 200 ? q.data.data : null;
  const valid = draft.title.trim().length >= 2 && draft.discipline && draft.level && draft.date;
  const busy = create.isPending || update.isPending;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setErr(null);
    const data = {
      title: draft.title.trim(),
      discipline: draft.discipline as FspDiscipline,
      level: draft.level as FspLevel,
      date: draft.date,
    };
    try {
      if (draft.id) await update.mutateAsync({ eventId: draft.id, data });
      else await create.mutateAsync({ data });
      setDraft(NEW_EVENT);
      await refresh();
    } catch (x) {
      setErr(errText(x));
    }
  }

  const edit = (ev: RegistryEventOut) =>
    setDraft({ id: ev.id, title: ev.title, discipline: ev.discipline, level: ev.level, date: ev.date });

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
      <section aria-label={R.tabs.events} className="order-2 flex flex-col gap-3 lg:order-1">
        {q.isLoading && <Skeleton className="h-32" />}
        {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
        {items && items.length === 0 && <EmptyState title={R.ev.empty} description={R.ev.emptyHint} />}
        {items?.map((ev) => (
          <Card key={ev.id}>
            <CardContent className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-16 font-semibold">{ev.title}</p>
                <p className="text-13 text-muted">
                  {DISCIPLINE[ev.discipline] ?? ev.discipline} · {LEVEL[ev.level] ?? ev.level} ·{" "}
                  {new Date(ev.date).toLocaleDateString("ru-RU")} · {R.ev.results(ev.results ?? 0)}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => edit(ev)}>
                  {R.edit}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onResults(ev.id)}>
                  {R.ev.toResults}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </section>
      <Card className="order-1 self-start lg:order-2">
        <CardContent>
          <form className="flex flex-col gap-3" aria-label={draft.id ? R.ev.editTitle : R.ev.create} onSubmit={(e) => void submit(e)}>
            <h2 className="text-16 font-semibold">{draft.id ? R.ev.editTitle : R.ev.create}</h2>
            <Field label={R.ev.name}>
              <FieldInput value={draft.title} maxLength={200} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </Field>
            <Field label={R.ev.discipline}>
              <Select aria-label={R.ev.discipline} options={DISCIPLINE_OPTIONS} value={draft.discipline} onChange={(v) => setDraft({ ...draft, discipline: v })} />
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={R.ev.level}>
                <Select aria-label={R.ev.level} options={LEVEL_OPTIONS} value={draft.level} onChange={(v) => setDraft({ ...draft, level: v })} />
              </Field>
              <Field label={R.ev.date}>
                <FieldInput type="date" value={draft.date} onChange={(e) => setDraft({ ...draft, date: e.target.value })} />
              </Field>
            </div>
            <ErrorLine text={err} />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" size="sm" disabled={!valid || busy}>
                {busy ? R.saving : R.save}
              </Button>
              {draft.id && (
                <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(NEW_EVENT)}>
                  {R.cancel}
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------------- участники
function Participants() {
  const refresh = useRefresh();
  const [search, setSearch] = useState("");
  const q = useRegistryParticipantsAdminFspParticipantsGet({ q: search.trim() || undefined, limit: 100 }, { query: { retry: false } });
  const create = useRegistryCreateParticipantAdminFspParticipantsPost();
  const importCsv = useRegistryImportParticipantsAdminFspParticipantsImportPost();
  const [draft, setDraft] = useState({ full_name: "", email: "", phone: "" });
  const [csv, setCsv] = useState("");
  const [report, setReport] = useState<CsvImportOut | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const items = q.data?.status === 200 ? q.data.data : null;
  const valid = draft.full_name.trim().length >= 2;

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setErr(null);
    try {
      await create.mutateAsync({
        data: { full_name: draft.full_name.trim(), email: draft.email.trim() || null, phone: draft.phone.trim() || null },
      });
      setDraft({ full_name: "", email: "", phone: "" });
      await refresh();
    } catch (x) {
      setErr(errText(x));
    }
  }

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!csv.trim()) return;
    setErr(null);
    try {
      const res = await importCsv.mutateAsync({ data: { csv } });
      setReport(res.data as CsvImportOut);
      setCsv("");
      await refresh();
    } catch (x) {
      setErr(errText(x));
    }
  }

  function readFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) void f.text().then(setCsv);
    e.target.value = "";
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
      <section aria-label={R.tabs.participants} className="order-2 flex flex-col gap-3 lg:order-1">
        <Field label={R.pt.search}>
          <FieldInput type="search" value={search} onChange={(e) => setSearch(e.target.value)} />
        </Field>
        {q.isLoading && <Skeleton className="h-32" />}
        {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
        {items && items.length === 0 && <EmptyState title={R.pt.empty} description={R.pt.emptyHint} />}
        {items && items.length > 0 && (
          <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline bg-card">
            {items.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                <div className="min-w-0">
                  <p className="text-14 font-semibold">{p.full_name}</p>
                  <p className="break-all text-13 text-muted">{[p.email, p.phone].filter(Boolean).join(" · ") || "—"}</p>
                </div>
                <div className="flex items-center gap-2">
                  {p.linked && <Badge variant="success">{R.pt.linked}</Badge>}
                  <span className="font-mono text-12 text-muted">{p.id}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
      <div className="order-1 flex flex-col gap-4 self-start lg:order-2">
        <Card>
          <CardContent>
            <form className="flex flex-col gap-3" aria-label={R.pt.create} onSubmit={(e) => void add(e)}>
              <h2 className="text-16 font-semibold">{R.pt.create}</h2>
              <Field label={R.pt.name}>
                <FieldInput value={draft.full_name} maxLength={200} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} />
              </Field>
              <Field label={R.pt.email} hint={R.pt.contactHint}>
                <FieldInput type="email" value={draft.email} maxLength={254} onChange={(e) => setDraft({ ...draft, email: e.target.value })} />
              </Field>
              <Field label={R.pt.phone}>
                <FieldInput type="tel" value={draft.phone} maxLength={32} onChange={(e) => setDraft({ ...draft, phone: e.target.value })} />
              </Field>
              <ErrorLine text={err} />
              <Button type="submit" size="sm" className="self-start" disabled={!valid || create.isPending}>
                {R.pt.add}
              </Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <form className="flex flex-col gap-3" aria-label={R.pt.importTitle} onSubmit={(e) => void upload(e)}>
              <h2 className="text-16 font-semibold">{R.pt.importTitle}</h2>
              <p className="text-13 text-muted">{R.pt.importHint}</p>
              <Field label={R.pt.csv}>
                <FieldTextarea rows={5} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={"ФИО;email;телефон\nИванова Мария;m@example.test;+7 900 000-00-00"} />
              </Field>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex min-h-9 cursor-pointer items-center rounded-lg border border-hairline px-3 text-14 font-semibold hover:border-brand-mid">
                  {R.pt.file}
                  <input type="file" accept=".csv,text/csv,text/plain" className="sr-only" onChange={readFile} />
                </label>
                <Button type="submit" size="sm" disabled={!csv.trim() || importCsv.isPending}>
                  {R.pt.import}
                </Button>
              </div>
              {report && (
                <div role="status" className="flex flex-col gap-1 text-14">
                  <p>{R.pt.imported(report.created, report.updated)}</p>
                  {report.errors.length > 0 && (
                    <>
                      <p className="text-error">{R.pt.importErrors}</p>
                      <ul className="list-inside list-disc text-13 text-muted">
                        {report.errors.slice(0, 20).map((x) => (
                          <li key={x.line}>
                            {R.pt.line(x.line)}: {R.pt.reason[x.reason] ?? x.reason}
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              )}
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------- результаты
function Results({ eventId, setEventId }: { eventId: string | null; setEventId: (v: string | null) => void }) {
  const refresh = useRefresh();
  const events = useRegistryEventsAdminFspEventsGet({ query: { retry: false } });
  const q = useRegistryResultsAdminFspResultsGet({ event_id: eventId ?? undefined }, { query: { enabled: Boolean(eventId), retry: false } });
  const upsert = useRegistryUpsertResultAdminFspResultsPut();
  const del = useRegistryDeleteResultAdminFspResultsResultIdDelete();
  const [participant, setParticipant] = useState<ComboOption | null>(null);
  const [place, setPlace] = useState<number | null>(null);
  const [team, setTeam] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const evs = events.data?.status === 200 ? events.data.data : [];
  const items = q.data?.status === 200 ? q.data.data : null;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!eventId || !participant) return;
    setErr(null);
    try {
      await upsert.mutateAsync({ data: { event_id: eventId, participant_id: participant.value, place, team: team.trim() || null } });
      setParticipant(null);
      setPlace(null);
      setTeam("");
      await refresh();
    } catch (x) {
      setErr(errText(x));
    }
  }

  async function remove(id: number) {
    setErr(null);
    try {
      await del.mutateAsync({ resultId: id });
      await refresh();
    } catch (x) {
      setErr(errText(x));
    }
  }

  if (events.isLoading) return <Skeleton className="h-32" />;
  if (evs.length === 0) return <EmptyState title={R.rs.noEvents} />;

  return (
    <div className="flex flex-col gap-4">
      <Field label={R.rs.event} className="max-w-xl">
        <Select
          aria-label={R.rs.event}
          placeholder={R.rs.pickEvent}
          options={evs.map((ev) => ({ value: ev.id, label: ev.title, hint: new Date(ev.date).toLocaleDateString("ru-RU") }))}
          value={eventId}
          onChange={(v) => setEventId(v)}
        />
      </Field>
      {eventId && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
          <section aria-label={R.tabs.results} className="order-2 flex flex-col gap-3 lg:order-1">
            {q.isLoading && <Skeleton className="h-24" />}
            {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
            {items && items.length === 0 && <EmptyState title={R.rs.empty} />}
            {items && items.length > 0 && (
              <ul className="flex flex-col divide-y divide-hairline rounded-lg border border-hairline bg-card">
                {items.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                    <div className="min-w-0">
                      <p className="text-14 font-semibold">{r.participant_name}</p>
                      <p className="text-13 text-muted">
                        {R.rs.placeShort(r.place)}
                        {r.team ? ` · ${r.team}` : ""}
                      </p>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => {
                          setParticipant({ value: r.participant_id, label: r.participant_name });
                          setPlace(r.place ?? null);
                          setTeam(r.team ?? "");
                        }}
                      >
                        {R.edit}
                      </Button>
                      <Button size="sm" variant="ghost" disabled={del.isPending} onClick={() => void remove(r.id)}>
                        {R.rs.remove}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <Card className="order-1 self-start lg:order-2">
            <CardContent>
              <form className="flex flex-col gap-3" aria-label={R.rs.add} onSubmit={(e) => void save(e)}>
                <Field label={R.rs.participant}>
                  <Combobox
                    aria-label={R.rs.participant}
                    placeholder={R.rs.pickParticipant}
                    loadOptions={participantSource}
                    selectedOptions={participant ? [participant] : []}
                    value={participant?.value ?? null}
                    onChange={(_, o) => setParticipant(o)}
                  />
                </Field>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={R.rs.place}>
                    <NumberInput value={place} onChange={setPlace} min={1} max={100000} />
                  </Field>
                  <Field label={R.rs.team} hint={R.rs.teamHint}>
                    <FieldInput value={team} maxLength={120} onChange={(e) => setTeam(e.target.value)} />
                  </Field>
                </div>
                <p className="text-13 text-muted">{R.rs.hint}</p>
                <ErrorLine text={err} />
                <Button type="submit" size="sm" className="self-start" disabled={!participant || upsert.isPending}>
                  {R.rs.add}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------- заявки
function RequestCard({ r }: { r: AdminFspRequestOut }) {
  const refresh = useRefresh();
  const accept = useRegistryAcceptRequestAdminFspRequestsRequestIdAcceptPost();
  const reject = useRegistryRejectRequestAdminFspRequestsRequestIdRejectPost();
  const suggestions = (r.candidates ?? []).map(participantOption);
  const [pick, setPick] = useState<ComboOption | null>(suggestions.length === 1 ? suggestions[0] : null);
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const busy = accept.isPending || reject.isPending;

  const source: OptionSource = async (query, signal) => {
    if (!query.trim()) return suggestions;
    return participantSource(query, signal);
  };

  async function run(fn: () => Promise<unknown>) {
    setErr(null);
    try {
      await fn();
      await refresh();
    } catch (x) {
      setErr(errText(x));
    }
  }

  return (
    <Card data-testid="fsp-request">
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-16 font-semibold">{r.full_name}</p>
            <p className="break-all text-13 text-muted">
              {R.rq.contacts}: {[r.email, r.phone].filter(Boolean).join(" · ") || "—"}
            </p>
            {r.event && (
              <p className="text-13 text-muted">
                {R.rq.event}: {r.event}
              </p>
            )}
            <p className="text-12 text-muted">{R.rq.created(r.created_at)}</p>
          </div>
          <Badge variant={r.status === "pending" ? "warning" : r.status === "accepted" ? "success" : "muted"}>{R.rq.status[r.status]}</Badge>
        </div>
        {r.status === "accepted" && r.participant_id && <p className="text-14">{R.rq.linkedTo(r.participant_id)}</p>}
        {r.status === "rejected" && r.reason && <p className="text-14">{r.reason}</p>}
        {r.status === "pending" && (
          <div className="grid gap-3 md:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Field label={R.rq.pick} hint={R.rq.pickHint}>
                <Combobox
                  aria-label={R.rq.pick}
                  options={suggestions}
                  loadOptions={source}
                  selectedOptions={pick ? [pick] : []}
                  value={pick?.value ?? null}
                  onChange={(_, o) => setPick(o)}
                />
              </Field>
              <Button size="sm" className="self-start" disabled={!pick || busy} onClick={() => pick && void run(() => accept.mutateAsync({ requestId: r.id, data: { participant_id: pick.value } }))}>
                {R.rq.accept}
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              <Field label={R.rq.reasonLabel} hint={R.rq.reasonHint}>
                <FieldTextarea rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
              </Field>
              <Button
                size="sm"
                variant="outline"
                className="self-start"
                disabled={reason.trim().length < 3 || busy}
                onClick={() => void run(() => reject.mutateAsync({ requestId: r.id, data: { reason: reason.trim() } }))}
              >
                {R.rq.reject}
              </Button>
            </div>
          </div>
        )}
        <ErrorLine text={err} />
      </CardContent>
    </Card>
  );
}

/** Заявки на привязку с фильтром по статусу — страница «Заявки ФСП» (E39-29). */
export function Requests() {
  const [status, setStatus] = useState<ReqStatus | "all">("pending");
  const q = useRegistryRequestsAdminFspRequestsGet(status === "all" ? undefined : { status }, { query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;
  return (
    <section aria-label={R.requests.title} className="flex flex-col gap-3">
      <div role="group" className="flex flex-wrap gap-1">
        {(["pending", "accepted", "rejected", "all"] as const).map((o) => (
          <button
            key={o}
            type="button"
            aria-pressed={status === o}
            onClick={() => setStatus(o)}
            className={`min-h-9 rounded-lg border px-3 text-14 font-semibold ${status === o ? "border-tint-200 bg-tint-100 text-brand-deep dark:text-brand-mid" : "border-hairline text-muted"}`}
          >
            {o === "all" ? R.rq.statusAll : R.rq.status[o]}
          </button>
        ))}
      </div>
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={R.rq.empty} description={R.rq.emptyHint} />}
      {items?.map((r) => <RequestCard key={`${r.id}-${r.status}`} r={r} />)}
    </section>
  );
}

/**
 * `/federation/registry` — реестр ФСП (E39-28, справочник): мероприятия, участники (руками и CSV), результаты.
 * Заявки на привязку — отдельная очередь `/federation/requests` (E39-29).
 */
export default function FspRegistry() {
  const [tab, setTab] = useState<Tab>("events");
  const [eventId, setEventId] = useState<string | null>(null);

  return (
    <div className={PAGE.wide}>
      <AdminPageHeader title={R.title} tip={R.lead} />
      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
        <TabsList className="max-w-full overflow-x-auto">
          <TabsTrigger value="events">{R.tabs.events}</TabsTrigger>
          <TabsTrigger value="participants">{R.tabs.participants}</TabsTrigger>
          <TabsTrigger value="results">{R.tabs.results}</TabsTrigger>
        </TabsList>
        <TabsContent value="events" className="pt-4">
          <Events
            onResults={(id) => {
              setEventId(id);
              setTab("results");
            }}
          />
        </TabsContent>
        <TabsContent value="participants" className="pt-4">
          <Participants />
        </TabsContent>
        <TabsContent value="results" className="pt-4">
          <Results eventId={eventId} setEventId={setEventId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
