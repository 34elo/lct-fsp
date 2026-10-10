import { useMemo, useState, type FormEvent } from "react";
import { Gloss } from "@/shared/Gloss";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Combobox, Dialog, DialogContent, DialogTitle, EmptyState, ErrorState, Field, Skeleton, useFieldProps } from "@fsp/ui";

import {
  getListProfessionsAdminProfessionsGetQueryKey,
  useCreateProfessionAdminProfessionsPost,
  useListProfessionsAdminProfessionsGet,
  useRetireProfessionAdminProfessionsSlugDelete,
  useUpdateProfessionAdminProfessionsSlugPatch,
} from "@/api/endpoints/admin/admin";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { ProfessionOut } from "@/api/model";
import { fieldClass } from "@/features/auth/ui";
import { buildWeights, nextId, problemText, professionErrors, weightRows, type WeightRow } from "./model";
import { T } from "./text";

const sel = (s: string) => `admin-prof-${s}`;

function In(p: React.InputHTMLAttributes<HTMLInputElement>) {
  const fp = useFieldProps();
  return <input {...fp} className={fieldClass} {...p} />;
}

interface SkillOpt {
  slug: string;
  name: string;
}

function Editor({ prof, skills, onDone }: { prof: ProfessionOut | null; skills: SkillOpt[]; onDone: (msg: string) => void }) {
  const qc = useQueryClient();
  const creating = prof === null;
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState(prof?.title ?? "");
  const [rows, setRows] = useState<WeightRow[]>(() => (prof ? weightRows(prof.skill_weights) : [{ id: nextId(), skill: "", weight: "0.5" }]));
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [serverErr, setServerErr] = useState<string | null>(null);
  const [confirmRetire, setConfirmRetire] = useState(false);

  const opts = (msg: string) => ({
    mutation: {
      onSuccess: () => {
        void qc.invalidateQueries({ queryKey: getListProfessionsAdminProfessionsGetQueryKey() });
        onDone(msg);
      },
      onError: (e: unknown) => setServerErr(problemText(e, T.prof.problem, T.saveError)),
    },
  });
  const create = useCreateProfessionAdminProfessionsPost(opts(T.prof.created));
  const update = useUpdateProfessionAdminProfessionsSlugPatch(opts(T.prof.saved));
  const retire = useRetireProfessionAdminProfessionsSlugDelete(opts(T.prof.retired));
  const busy = create.isPending || update.isPending || retire.isPending;

  const patch = (id: number, p: Partial<WeightRow>) => setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setServerErr(null);
    const found = professionErrors({ slug, title, rows }, creating);
    setErrs(found);
    if (Object.keys(found).length) return;
    const skill_weights = buildWeights(rows);
    if (prof) update.mutate({ slug: prof.slug, data: { title: title.trim(), skill_weights } });
    else create.mutate({ data: { slug, title: title.trim(), skill_weights } });
  };

  return (
    <div data-testid={sel("editor")}>
      <div>
        <form noValidate onSubmit={submit} className="flex flex-col gap-4">
          <DialogTitle className="break-all pr-10">{prof ? T.prof.editTitle(prof.slug) : T.prof.createTitle}</DialogTitle>
          {creating && (
            <Field label={T.prof.slug} hint={T.prof.slugHint} error={errs.slug}>
              <In data-testid={sel("slug")} value={slug} onChange={(e) => setSlug(e.target.value)} />
            </Field>
          )}
          <Field label={T.prof.name} error={errs.title}>
            <In data-testid={sel("title")} value={title} maxLength={80} onChange={(e) => setTitle(e.target.value)} />
          </Field>

          <fieldset className="flex flex-col gap-2" data-testid={sel("weights")}>
            <legend className="text-14 font-semibold">{T.prof.weights}</legend>
            <p className="text-13 text-muted">{T.prof.weightsHint}</p>
            {rows.map((r, i) => (
              <div key={r.id} className="grid grid-cols-[minmax(0,1fr)_5rem_auto] items-end gap-2" data-testid={sel(`row-${i}`)}>
                <div className="flex flex-col gap-1 text-13 text-muted">
                  <span>{T.prof.skill}</span>
                  <Combobox
                    data-testid={sel(`skill-${i}`)}
                    aria-label={T.prof.skill}
                    placeholder={T.prof.pickSkill}
                    value={r.skill || null}
                    onChange={(v) => patch(r.id, { skill: v ?? "" })}
                    options={[
                      ...(r.skill && !skills.some((s) => s.slug === r.skill) ? [{ value: r.skill, label: r.skill }] : []),
                      ...skills.map((s) => ({ value: s.slug, label: s.name, hint: s.slug })),
                    ]}
                  />
                </div>
                <label className="flex flex-col gap-1 text-13 text-muted">
                  {T.prof.weight}
                  <input className={fieldClass} inputMode="decimal" data-testid={sel(`weight-${i}`)} value={r.weight} onChange={(e) => patch(r.id, { weight: e.target.value })} />
                </label>
                <Button type="button" variant="ghost" size="sm" data-testid={sel(`remove-${i}`)} onClick={() => setRows((rs) => rs.filter((x) => x.id !== r.id))}>
                  {T.remove}
                </Button>
              </div>
            ))}
            {errs.weights && (
              <p role="alert" data-testid={sel("weights-error")} className="text-12 text-error">{errs.weights}</p>
            )}
            <div>
              <Button type="button" variant="outline" size="sm" data-testid={sel("add-skill")} onClick={() => setRows((rs) => [...rs, { id: nextId(), skill: "", weight: "0.5" }])}>
                {T.prof.addSkill}
              </Button>
            </div>
          </fieldset>

          {serverErr && (
            <p role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">{serverErr}</p>
          )}

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              {prof && !confirmRetire && (
                <Button type="button" variant="ghost" disabled={busy} data-testid={sel("retire")} onClick={() => setConfirmRetire(true)}>
                  {T.prof.retire}
                </Button>
              )}
              {prof && confirmRetire && (
                <div className="flex flex-wrap items-center gap-2" data-testid={sel("retire-confirm")}>
                  <span className="text-13">{T.prof.retireConfirm(prof.title)}</span>
                  <Button type="button" variant="outline" size="sm" disabled={busy} data-testid={sel("retire-yes")} onClick={() => retire.mutate({ slug: prof.slug })}>
                    {T.prof.retireYes}
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setConfirmRetire(false)}>{T.cancel}</Button>
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={() => onDone("")}>{T.cancel}</Button>
              <Button type="submit" disabled={busy} data-testid={sel("save")}>{T.save}</Button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

export function ProfessionsTab() {
  const q = useListProfessionsAdminProfessionsGet({ query: { retry: false } });
  const taxonomy = useGetTaxonomyTaxonomyGet();
  const skills = useMemo(() => (taxonomy.data?.data as { skills?: SkillOpt[] } | undefined)?.skills ?? [], [taxonomy.data]);
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [notice, setNotice] = useState("");
  const items = q.data?.status === 200 ? q.data.data : null;
  const current = editing && editing !== "new" ? (items?.find((p) => p.slug === editing) ?? null) : null;

  return (
    <div className="flex flex-col gap-4" data-testid={sel("tab")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-18 font-semibold">
          <Gloss k="category">{T.prof.listTitle}</Gloss>
        </h2>
        <Button type="button" data-testid={sel("create")} onClick={() => { setEditing("new"); setNotice(""); }}>
          {T.prof.create}
        </Button>
      </div>
      {notice && <p role="status" data-testid={sel("notice")} className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success-fg">{notice}</p>}
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.prof.empty} description={T.prof.emptyText} />}
      <p className="text-13 text-muted" data-testid={sel("growth")}>{T.prof.growth}</p>
      {items && items.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" data-testid={sel("list")}>
          {items.map((p) => (
            <li key={p.slug}>
              <button
                type="button"
                data-testid={sel(`edit-${p.slug}`)}
                aria-label={`${p.title}. ${T.prof.edit}`}
                onClick={() => { setEditing(p.slug); setNotice(""); }}
                className="flex h-full min-h-28 w-full flex-col items-start gap-2 rounded-xl border border-hairline bg-card p-4 text-left transition-colors hover:border-brand focus-visible:outline-2 focus-visible:outline-brand"
              >
                <span className="text-16 font-semibold" data-testid={sel(`title-${p.slug}`)}>{p.title}</span>
                <span className="break-all font-mono text-12 text-muted">{p.slug}</span>
                <span className="mt-auto flex flex-wrap gap-1">
                  {p.active === false && <Badge variant="muted" data-testid={sel(`hidden-${p.slug}`)}>{T.prof.hidden}</Badge>}
                  <Badge>{T.prof.skillsCount(Object.keys(p.skill_weights).length)}</Badge>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={editing !== null && (editing === "new" || current !== null)} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-h-[90dvh] max-w-2xl overflow-y-auto" aria-describedby={undefined}>
          {editing && (editing === "new" || current) && (
            <Editor
              key={editing}
              prof={current}
              skills={skills}
              onDone={(msg) => {
                setEditing(null);
                setNotice(msg);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
