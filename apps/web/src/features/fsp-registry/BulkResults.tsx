import { useState, type ChangeEvent } from "react";

import { Button, Dialog, DialogContent, DialogTitle, Field, Select, Textarea, useFieldProps, type ComboOption } from "@fsp/ui";

import { useRegistryImportResultsAdminFspRegistryImportPost } from "@/api/endpoints/admin/admin";
import type { FspDiscipline, FspLevel, ResultsImportIn, ResultsImportOut } from "@/api/model";
import { ApiError } from "@/api/mutator";

import { DISCIPLINE, LEVEL, R } from "./text";

const T = R.bulk;
const DISCIPLINE_OPTIONS: ComboOption[] = Object.entries(DISCIPLINE).map(([value, label]) => ({ value, label }));
const LEVEL_OPTIONS: ComboOption[] = Object.entries(LEVEL).map(([value, label]) => ({ value, label }));

function PasteArea(p: React.ComponentProps<typeof Textarea>) {
  return <Textarea {...useFieldProps()} {...p} />;
}

function downloadTemplate() {
  const blob = new Blob(["﻿", T.templateBody], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = T.templateName;
  a.click();
  URL.revokeObjectURL(url);
}

/** «Добавить списком» (E43-4): CSV или вставка → превью с построчной проверкой → запись. */
export function BulkResults({ onImported }: { onImported: () => Promise<unknown> | void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [discipline, setDiscipline] = useState<FspDiscipline>("algorithmic");
  const [level, setLevel] = useState<FspLevel>("regional");
  const [preview, setPreview] = useState<ResultsImportOut | null>(null);
  const [done, setDone] = useState<ResultsImportOut | null>(null);
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const [skip, setSkip] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = useRegistryImportResultsAdminFspRegistryImportPost();

  const reset = () => {
    setPreview(null);
    setDone(null);
    setConfirmed([]);
    setSkip(false);
    setErr(null);
  };
  const close = () => {
    setOpen(false);
    setText("");
    reset();
  };

  async function call(commit: boolean) {
    setErr(null);
    const data: ResultsImportIn = {
      csv: text,
      commit,
      skip_errors: skip,
      create_events: confirmed,
      default_discipline: discipline,
      default_level: level,
    };
    try {
      const res = (await run.mutateAsync({ data })).data as ResultsImportOut;
      if (commit) {
        setDone(res);
        setPreview(null);
        await onImported();
      } else {
        setPreview(res);
      }
    } catch (e) {
      setErr((e instanceof ApiError && e.code && T.problem[e.code]) || R.error);
    }
  }

  async function pickFile(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setText(await f.text());
    reset();
  }

  const errors = preview?.summary.errors ?? 0;
  const toWrite = preview ? preview.summary.created + preview.summary.updated : 0;
  const allConfirmed = !!preview && preview.new_events.every((e) => confirmed.includes(e.key));
  const canCommit = !!preview && toWrite > 0 && ((errors === 0 && allConfirmed) || skip);

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        {T.button}
      </Button>
      <Dialog open={open} onOpenChange={(o) => !o && close()}>
        <DialogContent className="max-h-[90dvh] max-w-3xl overflow-y-auto" aria-describedby={undefined}>
          <div className="flex flex-col gap-4" data-testid="registry-bulk">
            <DialogTitle>{T.title}</DialogTitle>
            {done ? (
              <>
                <p role="status" className="text-14">
                  {T.done(done.summary.created, done.summary.updated, done.summary.unchanged)}
                </p>
                <Button onClick={close}>{T.close}</Button>
              </>
            ) : (
              <>
                <p className="text-14 text-muted">{T.lead}</p>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="inline-flex min-h-9 cursor-pointer items-center rounded-lg border border-hairline px-3 text-14 font-semibold hover:border-brand-mid">
                    {T.file}
                    <input type="file" accept=".csv,text/csv,text/plain" className="sr-only" aria-label={T.file} onChange={(e) => void pickFile(e)} />
                  </label>
                  <Button variant="ghost" onClick={downloadTemplate}>
                    {T.template}
                  </Button>
                </div>
                <Field label={T.paste} hint={T.pasteHint}>
                  <PasteArea
                    rows={6}
                    value={text}
                    onChange={(e) => {
                      setText(e.target.value);
                      reset();
                    }}
                  />
                </Field>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={`${T.defaults}: ${R.ev.discipline.toLowerCase()}`}>
                    <Select
                      aria-label={R.ev.discipline}
                      options={DISCIPLINE_OPTIONS}
                      value={discipline}
                      onChange={(v) => {
                        setDiscipline(v as FspDiscipline);
                        reset();
                      }}
                    />
                  </Field>
                  <Field label={R.ev.level}>
                    <Select
                      aria-label={R.ev.level}
                      options={LEVEL_OPTIONS}
                      value={level}
                      onChange={(v) => {
                        setLevel(v as FspLevel);
                        reset();
                      }}
                    />
                  </Field>
                </div>
                {err && (
                  <p role="alert" className="text-14 text-error">
                    {err}
                  </p>
                )}
                <div>
                  <Button disabled={!text.trim() || run.isPending} onClick={() => void call(false)}>
                    {run.isPending && !preview ? T.checking : T.check}
                  </Button>
                </div>
                {preview && (
                  <Preview
                    preview={preview}
                    confirmed={confirmed}
                    setConfirmed={setConfirmed}
                    skip={skip}
                    setSkip={setSkip}
                    onCommit={() => void call(true)}
                    canCommit={canCommit}
                    busy={run.isPending}
                  />
                )}
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function Preview(p: {
  preview: ResultsImportOut;
  confirmed: string[];
  setConfirmed: (v: string[]) => void;
  skip: boolean;
  setSkip: (v: boolean) => void;
  onCommit: () => void;
  canCommit: boolean;
  busy: boolean;
}) {
  const { preview } = p;
  const toggle = (key: string) => p.setConfirmed(p.confirmed.includes(key) ? p.confirmed.filter((k) => k !== key) : [...p.confirmed, key]);
  return (
    <div className="flex flex-col gap-3" data-testid="bulk-preview">
      <p role="status" className="text-14 font-semibold">
        {T.summary(preview.summary)}
      </p>
      {preview.new_events.length > 0 && (
        <fieldset className="flex flex-col gap-1 rounded-lg border border-hairline px-3 py-2">
          <legend className="px-1 text-13 text-muted">{T.newEvents}</legend>
          {preview.new_events.map((ev) => (
            <label key={ev.key} className="flex items-center gap-2 text-14">
              <input type="checkbox" checked={p.confirmed.includes(ev.key)} onChange={() => toggle(ev.key)} />
              {T.newEvent(ev.title, ev.date, ev.rows)}
            </label>
          ))}
        </fieldset>
      )}
      <div className="max-h-72 overflow-auto rounded-lg border border-hairline">
        <table className="w-full text-left text-13">
          <thead className="sticky top-0 bg-card text-muted">
            <tr>
              <th className="px-2 py-1">{T.colLine}</th>
              <th className="px-2 py-1">{T.colWho}</th>
              <th className="px-2 py-1">{T.colEvent}</th>
              <th className="px-2 py-1">{T.colResult}</th>
              <th className="px-2 py-1">{T.colState}</th>
            </tr>
          </thead>
          <tbody>
            {preview.lines.map((l) => (
              <tr key={l.line} data-status={l.status} className={l.status === "error" ? "bg-error/10 text-error" : ""}>
                <td className="px-2 py-1">{l.line}</td>
                <td className="px-2 py-1">{l.participant_name ?? l.participant}</td>
                <td className="px-2 py-1">{l.event}</td>
                <td className="px-2 py-1">{l.result ?? ""}</td>
                <td className="px-2 py-1">{l.status === "error" ? (T.error[l.error ?? ""] ?? l.error) : T.action[l.action ?? "create"]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview.summary.errors > 0 && (
        <label className="flex items-center gap-2 text-14">
          <input type="checkbox" checked={p.skip} onChange={(e) => p.setSkip(e.target.checked)} />
          {T.skipErrors(preview.summary.errors)}
        </label>
      )}
      <div>
        <Button disabled={!p.canCommit || p.busy} onClick={p.onCommit}>
          {p.busy ? T.committing : T.commit(preview.summary.created + preview.summary.updated)}
        </Button>
      </div>
    </div>
  );
}
