import { useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Card, CardContent, cn, EmptyState, ErrorState, Field, Skeleton, useFieldProps } from "@fsp/ui";

import {
  getListCardsAdminSkillCardsGetQueryKey,
  useGetCardAdminSkillCardsSlugGet,
  useListCardsAdminSkillCardsGet,
  usePutCardAdminSkillCardsSlugPut,
} from "@/api/endpoints/admin/admin";
import type { CardOut } from "@/api/model";
import { fieldClass } from "@/features/auth/ui";
import { GRADES, buildCard, cardErrors, cardToForm, nextId, problemText, splitLines, type CardForm } from "./model";
import { T } from "./text";

const sel = (s: string) => `admin-card-${s}`;
const areaClass = `${fieldClass} h-auto min-h-24 py-2`;

function Area(p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const fp = useFieldProps();
  return <textarea {...fp} className={areaClass} {...p} />;
}

function CardEditor({ data, onSaved }: { data: CardOut; onSaved: (msg: string) => void }) {
  const qc = useQueryClient();
  const [f, setF] = useState<CardForm>(() => cardToForm(data.card));
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  const put = usePutCardAdminSkillCardsSlugPut({
    mutation: {
      onSuccess: (res) => {
        void qc.invalidateQueries({ queryKey: getListCardsAdminSkillCardsGetQueryKey() });
        void qc.invalidateQueries({ queryKey: [`/admin/skill-cards/${data.skill}`] });
        onSaved(T.card.saved(res.status === 200 ? res.data.version : data.version + 1));
      },
      onError: (e: unknown) => setServerErr(problemText(e, T.card.problem, T.saveError)),
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setServerErr(null);
    const found = cardErrors(f);
    setErrs(found);
    if (Object.keys(found).length) return;
    put.mutate({ slug: data.skill, data: buildCard(data.skill, data.card.type, f) });
  };

  return (
    <Card data-testid={sel("editor")}>
      <CardContent>
        <form noValidate onSubmit={submit} className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-16 font-semibold break-all">{T.card.editTitle(data.skill)}</h2>
            <div className="flex flex-wrap items-center gap-2">
              <Badge data-testid={sel("type")}>{T.skillType[data.card.type] ?? data.card.type}</Badge>
              <Badge variant="muted" data-testid={sel("source")} data-source={data.source}>
                {T.card.source[data.source] ?? data.source}
              </Badge>
              <span className="text-13 text-muted">{T.card.version(data.version)}</span>
            </div>
          </div>
          <p className="text-13 text-muted" data-testid={sel("source-note")}>{T.card.sourceNote[data.source] ?? ""}</p>

          <Field label={T.card.summary} hint={T.card.summaryHint} error={errs.summary}>
            <Area data-testid={sel("summary")} value={f.summary} maxLength={400} onChange={(e) => setF({ ...f, summary: e.target.value })} />
          </Field>

          <fieldset className="flex flex-col gap-3">
            <legend className="text-14 font-semibold">{T.card.levels}</legend>
            <p className="text-13 text-muted">{T.card.levelsHint}</p>
            {GRADES.map((g) => (
              <Field key={g} label={`${T.card.grade[g]} · ${T.card.count(splitLines(f.levels[g]).length)}`} error={errs[`levels-${g}`]}>
                <Area data-testid={sel(`levels-${g}`)} value={f.levels[g]} onChange={(e) => setF({ ...f, levels: { ...f.levels, [g]: e.target.value } })} />
              </Field>
            ))}
            {errs.levels && <p role="alert" data-testid={sel("levels-error")} className="text-12 text-error">{errs.levels}</p>}
          </fieldset>

          <fieldset className="flex flex-col gap-2" data-testid={sel("concepts")}>
            <legend className="text-14 font-semibold">{T.card.concepts}</legend>
            <p className="text-13 text-muted">{T.card.conceptsHint}</p>
            {f.concepts.map((c, i) => (
              <div key={c.id} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto] sm:items-end" data-testid={sel(`concept-${i}`)}>
                <label className="flex flex-col gap-1 text-13 text-muted">
                  {T.card.term}
                  <input className={fieldClass} data-testid={sel(`term-${i}`)} value={c.term} onChange={(e) => setF({ ...f, concepts: f.concepts.map((x) => (x.id === c.id ? { ...x, term: e.target.value } : x)) })} />
                </label>
                <label className="flex flex-col gap-1 text-13 text-muted">
                  {T.card.note}
                  <input className={fieldClass} data-testid={sel(`note-${i}`)} value={c.note} onChange={(e) => setF({ ...f, concepts: f.concepts.map((x) => (x.id === c.id ? { ...x, note: e.target.value } : x)) })} />
                </label>
                <Button type="button" variant="ghost" size="sm" data-testid={sel(`concept-remove-${i}`)} onClick={() => setF({ ...f, concepts: f.concepts.filter((x) => x.id !== c.id) })}>
                  {T.remove}
                </Button>
              </div>
            ))}
            {errs.concepts && <p role="alert" data-testid={sel("concepts-error")} className="text-12 text-error">{errs.concepts}</p>}
            <div>
              <Button type="button" variant="outline" size="sm" data-testid={sel("concept-add")} onClick={() => setF({ ...f, concepts: [...f.concepts, { id: nextId(), term: "", note: "" }] })}>
                {T.card.addConcept}
              </Button>
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2" data-testid={sel("misconceptions")}>
            <legend className="text-14 font-semibold">{T.card.misconceptions}</legend>
            <p className="text-13 text-muted">{T.card.misconceptionsHint}</p>
            {f.misconceptions.map((m, i) => (
              <div key={m.id} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end" data-testid={sel(`misc-${i}`)}>
                <label className="flex flex-col gap-1 text-13 text-muted">
                  {T.card.claim}
                  <input className={fieldClass} data-testid={sel(`claim-${i}`)} value={m.claim} onChange={(e) => setF({ ...f, misconceptions: f.misconceptions.map((x) => (x.id === m.id ? { ...x, claim: e.target.value } : x)) })} />
                </label>
                <label className="flex flex-col gap-1 text-13 text-muted">
                  {T.card.truth}
                  <input className={fieldClass} data-testid={sel(`truth-${i}`)} value={m.truth} onChange={(e) => setF({ ...f, misconceptions: f.misconceptions.map((x) => (x.id === m.id ? { ...x, truth: e.target.value } : x)) })} />
                </label>
                <Button type="button" variant="ghost" size="sm" data-testid={sel(`misc-remove-${i}`)} onClick={() => setF({ ...f, misconceptions: f.misconceptions.filter((x) => x.id !== m.id) })}>
                  {T.remove}
                </Button>
              </div>
            ))}
            {errs.misconceptions && <p role="alert" data-testid={sel("misconceptions-error")} className="text-12 text-error">{errs.misconceptions}</p>}
            <div>
              <Button type="button" variant="outline" size="sm" data-testid={sel("misc-add")} onClick={() => setF({ ...f, misconceptions: [...f.misconceptions, { id: nextId(), claim: "", truth: "" }] })}>
                {T.card.addMisconception}
              </Button>
            </div>
          </fieldset>

          {serverErr && <p role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">{serverErr}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onSaved("")}>{T.cancel}</Button>
            <Button type="submit" disabled={put.isPending} data-testid={sel("save")}>{T.save}</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function CardLoader({ slug, onSaved }: { slug: string; onSaved: (msg: string) => void }) {
  const q = useGetCardAdminSkillCardsSlugGet(slug, { query: { retry: false } });
  if (q.isLoading) return <Skeleton className="h-48" />;
  if (!q.data || q.data.status !== 200) return <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />;
  return <CardEditor key={`${slug}-${q.data.data.version}`} data={q.data.data} onSaved={onSaved} />;
}

export function CardsTab() {
  const q = useListCardsAdminSkillCardsGet({ query: { retry: false } });
  const [openSlug, setOpenSlug] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const items = q.data?.status === 200 ? q.data.data : null;

  return (
    <div className="flex flex-col gap-4" data-testid={sel("tab")}>
      <h2 className="text-18 font-semibold">{T.card.listTitle}</h2>
      {notice && <p role="status" data-testid={sel("notice")} className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success-fg">{notice}</p>}
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.card.empty} description={T.card.emptyText} />}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        {items && items.length > 0 && (
          <ul className="flex flex-col gap-2" data-testid={sel("list")}>
            {items.map((c) => (
              <li key={c.skill}>
                <Card className={cn(openSlug === c.skill && "border-brand")}>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-mono text-14 font-semibold break-all" data-testid={sel(`slug-${c.skill}`)}>{c.skill}</p>
                      <p className="text-13 text-muted" data-testid={sel(`meta-${c.skill}`)}>
                        {[T.skillType[c.type] ?? c.type, T.card.source[c.source] ?? c.source, T.card.version(c.version)].join(" · ")}
                      </p>
                    </div>
                    <Button type="button" size="sm" variant="outline" data-testid={sel(`open-${c.skill}`)} onClick={() => { setOpenSlug(c.skill); setNotice(""); }}>
                      {T.open}
                    </Button>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
        {openSlug && (
          <CardLoader
            key={openSlug}
            slug={openSlug}
            onSaved={(msg) => {
              setOpenSlug(null);
              setNotice(msg);
            }}
          />
        )}
      </div>
    </div>
  );
}
