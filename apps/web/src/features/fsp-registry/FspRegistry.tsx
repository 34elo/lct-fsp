import { useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent, type ComponentProps, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import {
  Badge,
  Button,
  Card,
  CardContent,
  Combobox,
  Dialog,
  DialogContent,
  DialogTitle,
  EmptyState,
  ErrorState,
  Field,
  FieldInput,
  NumberInput,
  ScrollTabs,
  SegmentedControl,
  Select,
  Skeleton,
  Tabs,
  TabsContent,
  TabsTrigger,
  Textarea,
  useFieldProps,
  type ComboOption,
  type OptionSource,
} from "@fsp/ui";

import {
  registryEventsAdminFspEventsGet,
  registryParticipantsAdminFspParticipantsGet,
  registryUpdateEventAdminFspEventsEventIdPatch,
  registryCreateEventAdminFspEventsPost,
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
import type { AdminFspRequestOut, CsvImportOut, FspDiscipline, FspLevel, RegistryEventOut, RegistryParticipantOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { AdminPageHeader } from "@/features/admin/PageHeader";
import { PAGE } from "@/shared/lib/page";

import { BulkResults } from "./BulkResults";
import { dropHeader, parseCsv } from "./csv";
import { DISCIPLINE, LEVEL, R } from "./text";

type Tab = "events" | "participants" | "results" | "requests";
type ReqStatus = "pending" | "accepted" | "rejected";

const TABS: Tab[] = ["events", "participants", "results", "requests"];
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

// ---------------------------------------------------------------------------------- формы создания
type EventDraft = { id: string | null; title: string; discipline: string | null; level: string | null; date: string };
const NEW_EVENT: EventDraft = { id: null, title: "", discipline: null, level: null, date: "" };

function EventForm({ edit, onDone }: { edit: RegistryEventOut | null; onDone: () => void }) {
  const refresh = useRefresh();
  const create = useRegistryCreateEventAdminFspEventsPost();
  const update = useRegistryUpdateEventAdminFspEventsEventIdPatch();
  const [draft, setDraft] = useState<EventDraft>(
    edit ? { id: edit.id, title: edit.title, discipline: edit.discipline, level: edit.level, date: edit.date } : NEW_EVENT,
  );
  const [err, setErr] = useState<string | null>(null);
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
      await refresh();
      onDone();
    } catch (x) {
      setErr(errText(x));
    }
  }

  return (
    <form className="flex flex-col gap-3" aria-label={draft.id ? R.ev.editTitle : R.ev.create} onSubmit={(e) => void submit(e)}>
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
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          {R.cancel}
        </Button>
        <Button type="submit" disabled={!valid || busy}>
          {busy ? R.saving : R.save}
        </Button>
      </div>
    </form>
  );
}

function ParticipantForm({ onDone }: { onDone: () => void }) {
  const refresh = useRefresh();
  const create = useRegistryCreateParticipantAdminFspParticipantsPost();
  const [draft, setDraft] = useState({ full_name: "", email: "", phone: "" });
  const [err, setErr] = useState<string | null>(null);
  const valid = draft.full_name.trim().length >= 2;

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setErr(null);
    try {
      await create.mutateAsync({
        data: { full_name: draft.full_name.trim(), email: draft.email.trim() || null, phone: draft.phone.trim() || null },
      });
      await refresh();
      onDone();
    } catch (x) {
      setErr(errText(x));
    }
  }

  return (
    <form className="flex flex-col gap-3" aria-label={R.pt.create} onSubmit={(e) => void add(e)}>
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
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          {R.cancel}
        </Button>
        <Button type="submit" disabled={!valid || create.isPending}>
          {R.pt.add}
        </Button>
      </div>
    </form>
  );
}

type ResultPreset = { eventId: string | null; participant: ComboOption | null; place: number | null; team: string };
const NEW_RESULT: ResultPreset = { eventId: null, participant: null, place: null, team: "" };

function ResultForm({ preset, onDone }: { preset: ResultPreset; onDone: () => void }) {
  const refresh = useRefresh();
  const events = useRegistryEventsAdminFspEventsGet({ query: { retry: false } });
  const upsert = useRegistryUpsertResultAdminFspResultsPut();
  const [eventId, setEventId] = useState<string | null>(preset.eventId);
  const [participant, setParticipant] = useState<ComboOption | null>(preset.participant);
  const [place, setPlace] = useState<number | null>(preset.place);
  const [team, setTeam] = useState(preset.team);
  const [err, setErr] = useState<string | null>(null);
  const evs = events.data?.status === 200 ? events.data.data : [];

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!eventId || !participant) return;
    setErr(null);
    try {
      await upsert.mutateAsync({ data: { event_id: eventId, participant_id: participant.value, place, team: team.trim() || null } });
      await refresh();
      onDone();
    } catch (x) {
      setErr(errText(x));
    }
  }

  if (events.isLoading) return <Skeleton className="h-32" />;
  if (evs.length === 0) return <EmptyState title={R.rs.noEvents} />;

  return (
    <form className="flex flex-col gap-3" aria-label={R.rs.add} onSubmit={(e) => void save(e)}>
      <Field label={R.rs.event}>
        <Select
          aria-label={R.rs.event}
          placeholder={R.rs.pickEvent}
          options={evs.map((ev) => ({ value: ev.id, label: ev.title, hint: new Date(ev.date).toLocaleDateString("ru-RU") }))}
          value={eventId}
          onChange={(v) => setEventId(v)}
        />
      </Field>
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
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>
          {R.cancel}
        </Button>
        <Button type="submit" disabled={!eventId || !participant || upsert.isPending}>
          {R.rs.add}
        </Button>
      </div>
    </form>
  );
}

type Kind = "event" | "participant" | "result";
type Dlg = { kind: Kind; event?: RegistryEventOut; result?: ResultPreset } | null;

/** Модалка «Создать»: сверху выбор, что создаём; при правке выбор скрыт. */
function CreateDialog({ dlg, setDlg }: { dlg: Dlg; setDlg: (d: Dlg) => void }) {
  const editing = Boolean(dlg?.event || dlg?.result);
  const close = () => setDlg(null);
  const title = dlg?.event ? R.ev.editTitle : dlg?.result ? R.rs.editTitle : R.create.title;
  return (
    <Dialog open={dlg !== null} onOpenChange={(o) => !o && close()}>
      <DialogContent className="max-h-[90dvh] max-w-lg overflow-y-auto" aria-describedby={undefined}>
        {dlg && (
          <div className="flex flex-col gap-4" data-testid="registry-create">
            <DialogTitle>{title}</DialogTitle>
            {!editing && (
              <SegmentedControl
                label={R.create.what}
                value={dlg.kind}
                onValueChange={(v) => setDlg({ kind: v as Kind })}
                options={[
                  { value: "event", label: R.create.event },
                  { value: "participant", label: R.create.participant },
                  { value: "result", label: R.create.result },
                ]}
              />
            )}
            {dlg.kind === "event" && <EventForm key={dlg.event?.id ?? "new"} edit={dlg.event ?? null} onDone={close} />}
            {dlg.kind === "participant" && <ParticipantForm onDone={close} />}
            {dlg.kind === "result" && <ResultForm key={dlg.result?.participant?.value ?? "new"} preset={dlg.result ?? NEW_RESULT} onDone={close} />}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------------- импорт CSV
type Report = { created: number; updated: number; errors: { line: number; reason: string }[] };

const lc = (s: string) => s.trim().toLowerCase();
const byLabel = (dict: Record<string, string>, v: string) =>
  Object.entries(dict).find(([k, label]) => lc(k) === lc(v) || lc(label) === lc(v))?.[0] ?? null;

function toIsoDate(v: string): string | null {
  const t = v.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(t)) return t;
  const m = t.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : null;
}

/** Импорт мероприятий: «название; дисциплина; уровень; дата». Совпали название и дата — запись правится. */
async function importEvents(rows: string[][]): Promise<Report> {
  const known = await registryEventsAdminFspEventsGet();
  const existing = known.status === 200 ? known.data : [];
  const rep: Report = { created: 0, updated: 0, errors: [] };
  const data = dropHeader(rows, (r) => toIsoDate(r[3] ?? "") !== null);
  const offset = rows.length - data.length;
  for (const [i, r] of data.entries()) {
    const line = i + 1 + offset;
    const [title = "", disc = "", lvl = "", date = ""] = r;
    const discipline = byLabel(DISCIPLINE, disc);
    const level = byLabel(LEVEL, lvl);
    const iso = toIsoDate(date);
    if (title.trim().length < 2) rep.errors.push({ line, reason: "no_title" });
    else if (!discipline) rep.errors.push({ line, reason: "bad_discipline" });
    else if (!level) rep.errors.push({ line, reason: "bad_level" });
    else if (!iso) rep.errors.push({ line, reason: "bad_date" });
    else {
      const body = { title: title.trim(), discipline: discipline as FspDiscipline, level: level as FspLevel, date: iso };
      const same = existing.find((e) => lc(e.title) === lc(body.title) && e.date === iso);
      try {
        if (same) {
          await registryUpdateEventAdminFspEventsEventIdPatch(same.id, body);
          rep.updated++;
        } else {
          await registryCreateEventAdminFspEventsPost(body);
          rep.created++;
        }
      } catch {
        rep.errors.push({ line, reason: "failed" });
      }
    }
  }
  return rep;
}

/** «Импорт CSV»: только выбор файла, формат подсказан рядом с кнопкой. */
function ImportButton({ tab, onReport }: { tab: "events" | "participants"; onReport: (r: Report | null, err?: string) => void }) {
  const refresh = useRefresh();
  const importParticipants = useRegistryImportParticipantsAdminFspParticipantsImportPost();
  const [busy, setBusy] = useState(false);

  async function pick(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    onReport(null);
    try {
      const text = await f.text();
      let rep: Report;
      if (tab === "participants") rep = (await importParticipants.mutateAsync({ data: { csv: text } })).data as CsvImportOut;
      else rep = await importEvents(parseCsv(text));
      onReport(rep);
      await refresh();
    } catch {
      onReport(null, R.error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <label
      className={`inline-flex min-h-9 cursor-pointer items-center rounded-lg border border-hairline px-3 text-14 font-semibold hover:border-brand-mid ${busy ? "pointer-events-none opacity-60" : ""}`}
    >
      {busy ? R.importing : R.importCsv}
      <input type="file" accept=".csv,text/csv,text/plain" className="sr-only" aria-label={R.importCsv} onChange={(e) => void pick(e)} />
    </label>
  );
}

// ---------------------------------------------------------------------------------- вкладки
function Events({ onEdit, onResults }: { onEdit: (ev: RegistryEventOut) => void; onResults: (eventId: string) => void }) {
  const q = useRegistryEventsAdminFspEventsGet({ query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;
  return (
    <section aria-label={R.tabs.events} className="flex flex-col gap-3">
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={R.ev.empty} description={R.ev.emptyHint} />}
      {items?.map((ev) => (
        <Card key={ev.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-16 font-semibold">{ev.title}</p>
              <p className="text-13 text-muted">
                {DISCIPLINE[ev.discipline] ?? ev.discipline} · {LEVEL[ev.level] ?? ev.level} · {new Date(ev.date).toLocaleDateString("ru-RU")} ·{" "}
                {R.ev.results(ev.results ?? 0)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => onEdit(ev)}>
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
  );
}

function Participants() {
  const [search, setSearch] = useState("");
  const q = useRegistryParticipantsAdminFspParticipantsGet({ q: search.trim() || undefined, limit: 100 }, { query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;
  return (
    <section aria-label={R.tabs.participants} className="flex flex-col gap-3">
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
  );
}

function Results({ eventId, setEventId, onEdit }: { eventId: string | null; setEventId: (v: string | null) => void; onEdit: (p: ResultPreset) => void }) {
  const refresh = useRefresh();
  const events = useRegistryEventsAdminFspEventsGet({ query: { retry: false } });
  const q = useRegistryResultsAdminFspResultsGet({ event_id: eventId ?? undefined }, { query: { enabled: Boolean(eventId), retry: false } });
  const del = useRegistryDeleteResultAdminFspResultsResultIdDelete();
  const [err, setErr] = useState<string | null>(null);
  const evs = events.data?.status === 200 ? events.data.data : [];
  const items = q.data?.status === 200 ? q.data.data : null;

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
        <section aria-label={R.tabs.results} className="flex flex-col gap-3">
          {q.isLoading && <Skeleton className="h-24" />}
          {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState onRetry={() => void q.refetch()} />}
          {items && items.length === 0 && <EmptyState title={R.rs.empty} />}
          <ErrorLine text={err} />
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
                      onClick={() =>
                        onEdit({ eventId: r.event_id, participant: { value: r.participant_id, label: r.participant_name }, place: r.place ?? null, team: r.team ?? "" })
                      }
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

/** Заявки на привязку с фильтром по статусу — вкладка «Заявки» реестра. */
function Requests() {
  const [status, setStatus] = useState<ReqStatus | "all">("pending");
  const q = useRegistryRequestsAdminFspRequestsGet(status === "all" ? undefined : { status }, { query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;
  return (
    <section aria-label={R.requests.title} className="flex flex-col gap-3">
      <p className="text-13 text-muted">{R.requests.lead}</p>
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

function ImportReport({ report, error }: { report: Report | null; error: string | null }) {
  if (error) return <ErrorLine text={error} />;
  if (!report) return null;
  return (
    <div role="status" className="flex flex-col gap-1 rounded-lg border border-hairline bg-card px-4 py-3 text-14">
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
  );
}

/**
 * `/federation/registry` — единый реестр ФСП: вкладки «Мероприятия · Участники · Результаты · Заявки»,
 * на первых трёх «Импорт CSV» (только выбор файла) и одна кнопка «Создать» с выбором, что создаём.
 */
export default function FspRegistry() {
  const [params, setParams] = useSearchParams();
  const asked = params.get("tab") as Tab | null;
  const tab: Tab = asked && TABS.includes(asked) ? asked : "events";
  const setTab = (t: Tab) => setParams(t === "events" ? {} : { tab: t }, { replace: true });
  const [eventId, setEventId] = useState<string | null>(null);
  const [dlg, setDlg] = useState<Dlg>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [reportErr, setReportErr] = useState<string | null>(null);
  const refreshAll = useRefresh();
  const pending = useRegistryRequestsAdminFspRequestsGet({ status: "pending" }, { query: { retry: false } });
  const waiting = pending.data?.status === 200 ? pending.data.data.length : undefined;

  const createKind: Kind = tab === "participants" ? "participant" : tab === "results" ? "result" : "event";
  const onReport = (r: Report | null, err?: string) => {
    setReport(r);
    setReportErr(err ?? null);
  };
  const switchTab = (t: string) => {
    onReport(null);
    setTab(t as Tab);
  };

  return (
    <div className={PAGE.wide}>
      <AdminPageHeader title={R.title} tip={R.lead}>
        <div className="flex flex-wrap items-center gap-2">
          {(tab === "events" || tab === "participants") && <ImportButton tab={tab} onReport={onReport} />}
          {tab === "results" && <BulkResults onImported={refreshAll} />}
          <Button onClick={() => setDlg({ kind: createKind })}>{R.create.button}</Button>
        </div>
      </AdminPageHeader>
      <Tabs value={tab} onValueChange={switchTab}>
        <ScrollTabs>
          <TabsTrigger value="events">{R.tabs.events}</TabsTrigger>
          <TabsTrigger value="participants">{R.tabs.participants}</TabsTrigger>
          <TabsTrigger value="results">{R.tabs.results}</TabsTrigger>
          <TabsTrigger value="requests" count={waiting || undefined}>
            {R.tabs.requests}
          </TabsTrigger>
        </ScrollTabs>
        {tab !== "requests" && <p className="pt-3 text-13 text-muted">{R.csvHint[tab]}</p>}
        <div className="pt-3">
          <ImportReport report={report} error={reportErr} />
        </div>
        <TabsContent value="events" className="pt-4">
          <Events
            onEdit={(ev) => setDlg({ kind: "event", event: ev })}
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
          <Results eventId={eventId} setEventId={setEventId} onEdit={(p) => setDlg({ kind: "result", result: p })} />
        </TabsContent>
        <TabsContent value="requests" className="pt-4">
          <Requests />
        </TabsContent>
      </Tabs>
      <CreateDialog dlg={dlg} setDlg={setDlg} />
    </div>
  );
}
