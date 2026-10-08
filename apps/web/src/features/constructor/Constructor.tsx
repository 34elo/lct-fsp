import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Badge, Button, Card, CardContent, cn, Field, useFieldProps } from "@fsp/ui";

import { useCreateFamilyFamiliesPost } from "@/api/endpoints/assessment/assessment";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { FamilyOut } from "@/api/model";
import { fieldClass } from "@/features/auth/ui";
import { useAuth } from "@/shared/lib/auth";
import { KINDS, buildSpec, emptyVar, initialForm, localErrors, problemView, type FormState, type ProblemView, type VarRow } from "./model";
import { T } from "./text";

const areaClass = `${fieldClass} h-auto min-h-24 py-2 font-mono text-14`;
type InProps = React.InputHTMLAttributes<HTMLInputElement>;
function In({ className, ...p }: InProps) {
  const fp = useFieldProps();
  return <input {...fp} className={cn(fieldClass, className)} {...p} />;
}
function Area(p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const fp = useFieldProps();
  return <textarea {...fp} className={areaClass} {...p} />;
}
function Sel({ className, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const fp = useFieldProps();
  return <select {...fp} className={cn(fieldClass, className)} {...p} />;
}
const sel = (s: string) => `constructor-${s}`;

function Row({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-3">{children}</div>;
}

function VarEditor({ row, onChange, onRemove }: { row: VarRow; onChange: (r: VarRow) => void; onRemove: () => void }) {
  const set = (p: Partial<VarRow>) => onChange({ ...row, ...p });
  return (
    <div data-testid={sel(`var-${row.id}`)} className="grid gap-2 rounded-lg border border-hairline p-3 sm:grid-cols-[1fr_9rem_2fr_auto] sm:items-end">
      <label className="flex flex-col gap-1 text-13 text-muted">
        {T.builder.varName}
        <input className={cn(fieldClass, "font-mono")} data-testid={sel(`var-name-${row.id}`)} value={row.name} onChange={(e) => set({ name: e.target.value })} />
      </label>
      <label className="flex flex-col gap-1 text-13 text-muted">
        {T.builder.varType}
        <select className={fieldClass} data-testid={sel(`var-type-${row.id}`)} value={row.type} onChange={(e) => set({ type: e.target.value as VarRow["type"] })}>
          <option value="range">{T.builder.varRange}</option>
          <option value="values">{T.builder.varValues}</option>
          <option value="expr">{T.builder.varExpr}</option>
        </select>
      </label>
      {row.type === "range" && (
        <div className="grid grid-cols-3 gap-2">
          {(["min", "max", "step"] as const).map((k) => (
            <label key={k} className="flex flex-col gap-1 text-13 text-muted">
              {k === "min" ? T.builder.varMin : k === "max" ? T.builder.varMax : T.builder.varStep}
              <input inputMode="decimal" className={fieldClass} data-testid={sel(`var-${k}-${row.id}`)} value={row[k]} onChange={(e) => set({ [k]: e.target.value })} />
            </label>
          ))}
        </div>
      )}
      {row.type === "values" && (
        <label className="flex flex-col gap-1 text-13 text-muted">
          {T.builder.varList}
          <input className={fieldClass} data-testid={sel(`var-list-${row.id}`)} value={row.list} onChange={(e) => set({ list: e.target.value })} />
        </label>
      )}
      {row.type === "expr" && (
        <label className="flex flex-col gap-1 text-13 text-muted">
          {T.builder.varFormula}
          <input className={cn(fieldClass, "font-mono")} data-testid={sel(`var-expr-${row.id}`)} value={row.expr} onChange={(e) => set({ expr: e.target.value })} />
        </label>
      )}
      <Button type="button" variant="ghost" onClick={onRemove} aria-label={T.builder.varRemove} data-testid={sel(`var-remove-${row.id}`)}>
        {T.builder.varRemove}
      </Button>
    </div>
  );
}

function KeyEditor({ f, set }: { f: FormState; set: (p: Partial<FormState>) => void }) {
  const area = (key: keyof FormState, label: string, testid: string) => (
    <Field label={label}>
      <Area data-testid={testid} value={f[key] as string} onChange={(e) => set({ [key]: e.target.value })} />
    </Field>
  );
  const line = (key: keyof FormState, label: string, testid: string, hint?: string) => (
    <Field label={label} hint={hint}>
      <In data-testid={testid} value={f[key] as string} onChange={(e) => set({ [key]: e.target.value })} />
    </Field>
  );
  switch (f.kind) {
    case "exact":
    case "estimate":
      return (
        <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
          <Field label={T.builder.answer} hint={T.builder.answerHint}>
            <In className="font-mono" data-testid={sel("answer")} value={f.answer} onChange={(e) => set({ answer: e.target.value })} />
          </Field>
          {f.kind === "exact" && line("precision", T.builder.precision, sel("precision"))}
        </div>
      );
    case "choice":
      return (
        <>
          {area("options", T.builder.options, sel("options"))}
          {line("correct", T.builder.correct, sel("correct"))}
        </>
      );
    case "find_bug":
      return (
        <>
          {area("lines", T.builder.lines, sel("lines"))}
          {line("bugLines", T.builder.bugLines, sel("bug-lines"))}
        </>
      );
    case "order":
      return area("steps", T.builder.steps, sel("steps"));
    case "sjt":
      return area("actions", T.builder.actions, sel("actions"));
    case "open":
      return area("rubric", T.builder.rubric, sel("rubric"));
  }
}

function exampleText(ex: Record<string, unknown>): { stem: string; key: string; options: string[] } {
  const options = Array.isArray(ex.options) ? ex.options.map(String) : [];
  const stem = typeof ex.stem === "string" ? ex.stem : "";
  const k = ex.key;
  const key = typeof k === "string" || typeof k === "number" ? String(k) : k === undefined || k === null ? "" : JSON.stringify(k);
  return { stem, key, options };
}

export function FamilyPreview({ family }: { family: FamilyOut | null }) {
  if (!family)
    return (
      <p data-testid={sel("preview-empty")} className="text-14 text-muted">
        {T.preview.empty}
      </p>
    );
  const auto = family.autocheck as { ok?: boolean; seeds?: number };
  const draft = family.key_draft as Record<string, unknown> | null;
  return (
    <div data-testid={sel("preview")} className="flex flex-col gap-3">
      <p role="status" className="text-14 font-semibold text-success">
        {T.preview.created}
      </p>
      <div className="flex flex-wrap items-center gap-2 text-13">
        <span className="text-muted">{T.preview.status}</span>
        <Badge variant="warning" data-testid={sel("status")}>{T.status[family.status] ?? family.status}</Badge>
        <span className="text-muted">{T.preview.keyStatus}</span>
        <Badge variant={family.key_status === "approved" ? "success" : "warning"} data-testid={sel("key-status")}>
          {T.keyStatus[family.key_status] ?? family.key_status}
        </Badge>
      </div>
      <p className="text-14" data-testid={sel("autocheck")}>
        <span className="font-semibold">{T.preview.autocheck}: </span>
        {auto.ok ? T.preview.autocheckOk(auto.seeds ?? 200) : "—"}
      </p>
      {draft && (
        <div data-testid={sel("key-draft")} className="rounded-lg border border-hairline p-3 text-13">
          <p className="font-semibold">{T.preview.keyDraft}</p>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap font-mono text-13">{JSON.stringify(draft)}</pre>
          <p className="mt-1 text-muted">{T.preview.keyDraftNote}</p>
        </div>
      )}
      <ol className="flex flex-col gap-2">
        {(family.examples ?? []).map((ex, i) => {
          const v = exampleText(ex);
          return (
            <li key={i} data-testid={sel(`example-${i}`)} className="rounded-lg border border-hairline p-3">
              <p className="text-13 text-muted">{T.preview.variant(i + 1)}</p>
              <p className="whitespace-pre-wrap text-14">{v.stem}</p>
              {v.options.length > 0 && (
                <ul className="mt-1 list-disc pl-5 text-14">
                  {v.options.map((o, j) => (
                    <li key={j}>{o}</li>
                  ))}
                </ul>
              )}
              {v.key && (
                <p className="mt-1 text-13">
                  <span className="text-muted">{T.preview.key}: </span>
                  <span className="font-mono">{v.key}</span>
                </p>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** K1: конструктор задания. Работодатель — задание компании, админ ФСП — задание банка. */
export default function Constructor() {
  const nav = useNavigate();
  const { role } = useAuth();
  const [f, setF] = useState<FormState>(initialForm);
  const [nextVar, setNextVar] = useState(1);
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [problem, setProblem] = useState<ProblemView | null>(null);
  const [created, setCreated] = useState<FamilyOut | null>(null);

  const taxonomy = useGetTaxonomyTaxonomyGet();
  const skills = useMemo(() => (taxonomy.data?.data as { skills?: { slug: string; name: string }[] } | undefined)?.skills ?? [], [taxonomy.data]);
  const create = useCreateFamilyFamiliesPost({
    mutation: {
      onSuccess: (res) => {
        if (res.status === 201) {
          setCreated(res.data);
          setProblem(null);
        }
      },
      onError: (e) => {
        setCreated(null);
        setProblem(problemView(e));
      },
    },
  });

  const set = (p: Partial<FormState>) => setF((s) => ({ ...s, ...p }));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const le = localErrors(f);
    setErrs(le);
    if (Object.keys(le).length > 0) return;
    setProblem(null);
    create.mutate({ data: buildSpec(f) });
  };
  const lead = role === "fsp_admin" ? T.builder.leadAdmin : role === "employer" ? T.builder.leadEmployer : T.builder.lead;

  return (
    <div data-testid={sel("page")} className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{T.builder.title}</h1>
        <p className="text-14 text-muted">{lead}</p>
      </header>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <form onSubmit={submit} noValidate className="flex flex-col gap-4" data-testid={sel("form")}>
          <Card>
            <CardContent className="flex flex-col gap-4">
              <Field label={T.builder.name} error={errs.title}>
                <In data-testid={sel("title")} value={f.title} onChange={(e) => set({ title: e.target.value })} />
              </Field>
              <Row>
                <Field label={T.builder.skill} hint={T.builder.skillHint} error={errs.skill}>
                  <In list="constructor-skills" data-testid={sel("skill")} value={f.skill} onChange={(e) => set({ skill: e.target.value })} />
                </Field>
                <Field label={T.builder.level}>
                  <Sel data-testid={sel("level")} value={f.level} onChange={(e) => set({ level: Number(e.target.value) })}>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n} value={n}>{`${n} из 5`}</option>
                    ))}
                  </Sel>
                </Field>
                <Field label={T.builder.time} hint={T.builder.timeHint}>
                  <In inputMode="numeric" data-testid={sel("time")} value={f.timeLimit} onChange={(e) => set({ timeLimit: e.target.value })} />
                </Field>
              </Row>
              <datalist id="constructor-skills">
                {skills.map((s) => (
                  <option key={s.slug} value={s.slug}>{s.name}</option>
                ))}
              </datalist>
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-1 text-14 font-semibold">{T.builder.kind}</legend>
                <div role="radiogroup" aria-label={T.builder.kind} className="flex flex-wrap gap-2">
                  {KINDS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      role="radio"
                      aria-checked={f.kind === k}
                      title={T.builder.kindLabel[k]}
                      data-testid={sel(`kind-${k}`)}
                      onClick={() => set({ kind: k })}
                      className={cn("h-9 rounded-lg border px-3 font-mono text-14 font-semibold", f.kind === k ? "border-brand bg-brand text-on-brand" : "border-hairline bg-card hover:bg-tint-50")}
                    >
                      {k}
                    </button>
                  ))}
                </div>
              </fieldset>
              <Field label={T.builder.stem} hint={T.builder.stemHint} error={errs.stem}>
                <Area data-testid={sel("stem")} value={f.stem} onChange={(e) => set({ stem: e.target.value })} />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-3">
              <h2 className="text-16 font-semibold">{T.builder.vars}</h2>
              {f.vars.map((v) => (
                <VarEditor
                  key={v.id}
                  row={v}
                  onChange={(r) => set({ vars: f.vars.map((x) => (x.id === r.id ? r : x)) })}
                  onRemove={() => set({ vars: f.vars.filter((x) => x.id !== v.id) })}
                />
              ))}
              <div>
                <Button
                  type="button"
                  variant="outline"
                  data-testid={sel("var-add")}
                  onClick={() => {
                    set({ vars: [...f.vars, emptyVar(nextVar)] });
                    setNextVar(nextVar + 1);
                  }}
                >
                  {T.builder.varAdd}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="flex flex-col gap-3">
              <h2 className="text-16 font-semibold">
                {T.builder.key} · <span className="font-mono">{f.kind}</span>
              </h2>
              <p className="text-13 text-muted">{T.builder.keyOptional}</p>
              <KeyEditor f={f} set={set} />
            </CardContent>
          </Card>

          {problem && (
            <div role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-sm text-error">
              <span data-testid={sel("error-code")} data-code={problem.code}>{problem.message}</span>
              {problem.details.length > 0 && (
                <ul className="mt-1 list-disc pl-5" data-testid={sel("error-details")}>
                  {problem.details.map((d, i) => (
                    <li key={i}>{d}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-13 text-muted">{T.builder.saveHint}</p>
            <div className="flex gap-2">
              <Button type="button" variant="ghost" onClick={() => nav(-1)} data-testid={sel("cancel")}>
                {T.builder.cancel}
              </Button>
              <Button type="submit" disabled={create.isPending} data-testid={sel("save")}>
                {create.isPending ? T.builder.saving : T.builder.save}
              </Button>
            </div>
          </div>
        </form>

        <aside aria-label={T.preview.title} className="lg:sticky lg:top-4 lg:self-start">
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h2 className="text-16 font-semibold">{T.preview.title}</h2>
              <FamilyPreview family={created} />
              {created && role === "employer" && (
                <Link to="/employer/tasks" className="text-14 font-semibold text-brand-deep dark:text-brand-mid underline">
                  {T.preview.toTasks}
                </Link>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
