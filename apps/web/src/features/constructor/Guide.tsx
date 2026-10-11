import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, Card, CardContent, cn, Combobox, Field, Select } from "@fsp/ui";

import { useCreateFamilyFamiliesPost } from "@/api/endpoints/assessment/assessment";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { FamilyOut } from "@/api/model";
import { PAGE } from "@/shared/lib/page";
import { Area, FamilyPreview, In, KeyEditor, ReadyAction, VarEditor } from "./Constructor";
import { FIELD_STEP, GUIDE_STEPS, TEMPLATES, sampleStem, stepErrors } from "./guide-model";
import { G } from "./guide-text";
import { KINDS, buildSpec, emptyVar, initialForm, localErrors, problemView, type FormState, type ProblemView } from "./model";
import { T } from "./text";

const sel = (s: string) => `guide-${s}`;

function Examples() {
  return (
    <div className="grid gap-2 sm:grid-cols-2" data-testid={sel("examples")}>
      {(["good", "bad"] as const).map((k) => (
        <div key={k} className={cn("rounded-lg border p-3 text-13", k === "good" ? "border-success" : "border-error")}>
          <p className={cn("font-semibold", k === "good" ? "text-success" : "text-error")}>{G.s3[k]}</p>
          <p className="mt-1 font-mono text-13">{G.examples[k][0]}</p>
          <p className="mt-1 text-muted">{G.examples[k][1]}</p>
        </div>
      ))}
    </div>
  );
}

function CandidateView({ f }: { f: FormState }) {
  const stem = sampleStem(f);
  const opts = f.kind === "choice" ? f.options.split("\n").map((x) => x.trim()).filter(Boolean) : [];
  const lines = f.kind === "find_bug" ? f.lines.split("\n") : [];
  return (
    <div data-testid={sel("candidate")} className="flex flex-col gap-2 rounded-lg border border-hairline p-3">
      <p className="text-12 text-muted">
        {T.builder.kindLabel[f.kind]} · {f.timeLimit || "—"} с
      </p>
      <p className="whitespace-pre-wrap break-words text-14" data-testid={sel("candidate-stem")}>
        {stem.trim() || <span className="text-muted">{G.s3.stem}…</span>}
      </p>
      {opts.length > 0 && (
        <ul className="list-disc pl-5 text-14">
          {opts.map((o, i) => (
            <li key={i}>{o}</li>
          ))}
        </ul>
      )}
      {lines.length > 0 && (
        <pre className="overflow-x-auto rounded-sm bg-tint-50 p-2 font-mono text-13">{lines.map((l, i) => `${i + 1}  ${l}`).join("\n")}</pre>
      )}
      {f.vars.length > 0 && <p className="text-12 text-muted">{G.varsSample}</p>}
    </div>
  );
}

/** Мастер «Как сделать задание»: 5 шагов, 3 шаблона, примеры, предпросмотр. */
export default function Guide() {
  const nav = useNavigate();
  const [step, setStep] = useState(1);
  const [f, setF] = useState<FormState>(initialForm);
  const [tpl, setTpl] = useState<string | null>(null);
  const [nextVar, setNextVar] = useState(10);
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
  const pickTemplate = (id: string | null) => {
    setTpl(id);
    setErrs({});
    setF(id ? TEMPLATES.find((t) => t.id === id)!.form : initialForm());
  };
  const go = (to: number) => {
    setErrs({});
    setStep(to);
  };
  const next = () => {
    const e = stepErrors(f, step);
    setErrs(e);
    if (Object.keys(e).length === 0) go(step + 1);
  };
  const save = () => {
    const e = localErrors(f);
    setErrs(e);
    if (Object.keys(e).length > 0) return;
    setProblem(null);
    create.mutate({ data: buildSpec(f) });
  };
  const errFields = Object.keys(errs);

  return (
    <div className={PAGE.wide} data-testid={sel("page")}>
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{G.title}</h1>
        <p className="text-14 text-muted">{G.lead}</p>
      </header>
      <ol aria-label={G.stepsLabel} className="flex gap-2 overflow-x-auto" data-testid={sel("steps")}>
        {G.steps.map((s, i) => (
          <li key={s} aria-current={step === i + 1 ? "step" : undefined} data-testid={sel(`step-${i + 1}`)}>
            <button
              type="button"
              disabled={created !== null || i + 1 > step}
              onClick={() => go(i + 1)}
              className={cn(
                "h-9 whitespace-nowrap rounded-full border px-3 text-13 font-semibold disabled:cursor-default",
                step === i + 1 ? "border-brand bg-brand text-on-brand" : i + 1 < step ? "border-brand text-brand-deep dark:text-brand-mid" : "border-hairline text-muted",
              )}
            >
              {i + 1}. {s}
            </button>
          </li>
        ))}
      </ol>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardContent className="flex flex-col gap-4">
            <h2 className="text-16 font-semibold">
              <span className="text-muted">{G.stepOf(step, GUIDE_STEPS)} · </span>
              {G.steps[step - 1]}
            </h2>

            {step === 1 && (
              <>
                <p className="text-14 text-muted">{G.s1.lead}</p>
                <div className="flex flex-col gap-2" data-testid={sel("templates")}>
                  <p className="text-13 font-semibold">{G.tplTitle}</p>
                  <div className="grid gap-2 sm:grid-cols-4">
                    {[...TEMPLATES, null].map((t) => (
                      <button
                        key={t?.id ?? "scratch"}
                        type="button"
                        aria-pressed={tpl === (t?.id ?? null)}
                        data-testid={sel(`tpl-${t?.id ?? "scratch"}`)}
                        onClick={() => pickTemplate(t?.id ?? null)}
                        className={cn("flex flex-col items-start gap-0.5 rounded-lg border p-3 text-left", tpl === (t?.id ?? null) ? "border-brand bg-tint-50" : "border-hairline bg-card hover:bg-tint-50")}
                      >
                        <span className="text-14 font-semibold">{t?.name ?? G.tplScratch}</span>
                        <span className="text-12 text-muted">{t?.hint ?? G.tplHint}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <Field label={G.s1.name} hint={G.s1.nameHint} error={errs.title}>
                  <In data-testid={sel("title")} value={f.title} onChange={(e) => set({ title: e.target.value })} />
                </Field>
                <div className="grid gap-3 sm:grid-cols-3">
                  <Field label={G.s1.skill} hint={T.builder.skillHint} error={errs.skill}>
                    <Combobox
                      data-testid={sel("skill")}
                      value={f.skill || null}
                      onChange={(v) => set({ skill: v ?? "" })}
                      options={skills.map((s) => ({ value: s.slug, label: s.name, hint: s.slug }))}
                      creatable
                      createLabel={(q) => `Взять «${q}»`}
                    />
                  </Field>
                  <Field label={G.s1.level}>
                    <Select value={String(f.level)} onChange={(v) => v && set({ level: Number(v) })} options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: `${n} из 5` }))} />
                  </Field>
                  <Field label={G.s1.time} hint={T.builder.timeHint}>
                    <In inputMode="numeric" data-testid={sel("time")} value={f.timeLimit} onChange={(e) => set({ timeLimit: e.target.value })} />
                  </Field>
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <p className="text-14 text-muted">{G.s2.lead}</p>
                <div role="radiogroup" aria-label={T.builder.kind} className="grid gap-2 sm:grid-cols-2">
                  {KINDS.map((k) => (
                    <button
                      key={k}
                      type="button"
                      role="radio"
                      aria-checked={f.kind === k}
                      data-testid={sel(`kind-${k}`)}
                      onClick={() => set({ kind: k })}
                      className={cn("flex flex-col items-start gap-0.5 rounded-lg border p-3 text-left", f.kind === k ? "border-brand bg-tint-50" : "border-hairline bg-card hover:bg-tint-50")}
                    >
                      <span className="text-14 font-semibold">{T.builder.kindLabel[k]}</span>
                      <span className="text-12 text-muted">{k === "open" ? G.s2.manual : G.s2.auto}</span>
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <p className="text-14 text-muted">{G.s3.lead}</p>
                <Field label={G.s3.stem} hint={T.builder.stemHint} error={errs.stem}>
                  <Area data-testid={sel("stem")} value={f.stem} onChange={(e) => set({ stem: e.target.value })} />
                </Field>
                <h3 className="text-14 font-semibold">{G.s3.varsTitle}</h3>
                {f.vars.map((r) => (
                  <VarEditor key={r.id} row={r} onChange={(x) => set({ vars: f.vars.map((y) => (y.id === x.id ? x : y)) })} onRemove={() => set({ vars: f.vars.filter((y) => y.id !== r.id) })} />
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
                <Examples />
              </>
            )}

            {step === 4 && (
              <>
                <p className="text-14 text-muted">{G.s4.lead}</p>
                <KeyEditor f={f} set={set} />
              </>
            )}

            {step === 5 && (
              <>
                <p className="text-14 text-muted">{G.s5.lead}</p>
                <div data-testid={sel("checklist")}>
                  <p className="text-13 font-semibold">{G.s5.checklist}</p>
                  <ul className="mt-1 list-disc pl-5 text-14">
                    {G.check.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                </div>
                {errFields.length > 0 && (
                  <div role="alert" data-testid={sel("missing")} className="rounded-lg bg-error-bg px-3 py-2 text-sm text-error">
                    {G.s5.missing}:
                    <ul className="mt-1 list-disc pl-5">
                      {errFields.map((k) => (
                        <li key={k}>
                          <button type="button" className="underline" onClick={() => go(FIELD_STEP[k] ?? 1)}>
                            {errs[k]}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {problem && (
                  <div role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-sm text-error">
                    <span data-testid={sel("error-code")} data-code={problem.code}>
                      {problem.message}
                    </span>
                    {problem.details.length > 0 && (
                      <ul className="mt-1 list-disc pl-5">
                        {problem.details.map((d, i) => (
                          <li key={i}>{d}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </>
            )}

            <div className="flex flex-wrap items-center justify-between gap-2">
              <Link to="/employer/families/new" className="text-13 text-muted underline" data-testid={sel("full")}>
                {G.toFull}
              </Link>
              <div className="flex gap-2">
                {step > 1 && !created && (
                  <Button type="button" variant="ghost" onClick={() => go(step - 1)} data-testid={sel("back")}>
                    {G.back}
                  </Button>
                )}
                {step < GUIDE_STEPS && (
                  <Button type="button" onClick={next} data-testid={sel("next")}>
                    {G.next}
                  </Button>
                )}
                {step === GUIDE_STEPS && !created && (
                  <Button type="button" disabled={create.isPending} onClick={save} data-testid={sel("save")}>
                    {create.isPending ? G.saving : G.save}
                  </Button>
                )}
                {created && (
                  <Button type="button" onClick={() => nav("/employer/tasks")} data-testid={sel("done")}>
                    {G.toTasks}
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <aside aria-label={T.preview.title} className="lg:sticky lg:top-4 lg:self-start">
          <Card>
            <CardContent className="flex flex-col gap-3">
              <h2 className="text-16 font-semibold">{T.preview.title}</h2>
              {created ? (
                <>
                  <FamilyPreview family={created} />
                  <ReadyAction family={created} onChange={setCreated} />
                </>
              ) : (
                <CandidateView f={f} />
              )}
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
