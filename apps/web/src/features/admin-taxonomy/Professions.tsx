import { useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, Card, CardContent, cn, EmptyState, ErrorState, Field, Skeleton, useFieldProps } from "@fsp/ui";

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
    <Card data-testid={sel("editor")}>
      <CardContent>
        <form noValidate onSubmit={submit} className="flex flex-col gap-4">
          <h2 className="text-16 font-semibold break-all">{prof ? T.prof.editTitle(prof.slug) : T.prof.createTitle}</h2>
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
                <label className="flex flex-col gap-1 text-13 text-muted">
                  {T.prof.skill}
                  <select className={fieldClass} data-testid={sel(`skill-${i}`)} value={r.skill} onChange={(e) => patch(r.id, { skill: e.target.value })}>
                    <option value="">{T.prof.pickSkill}</option>
                    {r.skill && !skills.some((s) => s.slug === r.skill) && <option value={r.skill}>{r.skill}</option>}
                    {skills.map((s) => (
                      <option key={s.slug} value={s.slug}>{s.name}</option>
                    ))}
                  </select>
                </label>
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
      </CardContent>
    </Card>
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
        <h2 className="text-18 font-semibold">{T.prof.listTitle}</h2>
        <Button type="button" data-testid={sel("create")} onClick={() => { setEditing("new"); setNotice(""); }}>
          {T.prof.create}
        </Button>
      </div>
      {notice && <p role="status" data-testid={sel("notice")} className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success-fg">{notice}</p>}
      {q.isLoading && <Skeleton className="h-32" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && <EmptyState title={T.prof.empty} description={T.prof.emptyText} />}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {items && items.length > 0 && (
          <ul className="flex flex-col gap-2" data-testid={sel("list")}>
            {items.map((p) => (
              <li key={p.slug}>
                <Card className={cn(editing === p.slug && "border-brand")}>
                  <CardContent className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-14 font-semibold" data-testid={sel(`title-${p.slug}`)}>{p.title}</p>
                      <p className="font-mono text-13 text-muted break-all">{p.slug}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {p.active === false && <Badge variant="muted" data-testid={sel(`hidden-${p.slug}`)}>{T.prof.hidden}</Badge>}
                      <Badge>{T.prof.skillsCount(Object.keys(p.skill_weights).length)}</Badge>
                      <Button type="button" size="sm" variant="outline" data-testid={sel(`edit-${p.slug}`)} onClick={() => { setEditing(p.slug); setNotice(""); }}>
                        {T.prof.edit}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        )}
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
      </div>
    </div>
  );
}
