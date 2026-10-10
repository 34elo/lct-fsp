import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, cn, Combobox, Dialog, DialogContent, DialogDescription, DialogTitle, Field, NumberInput, Select } from "@fsp/ui";

import {
  getAdmissionQueueAdminFamiliesGetQueryKey,
  getFamilyOrdersAdminAssessmentGenerateGetQueryKey,
  useFamilyOrdersAdminAssessmentGenerateGet,
  useGenerateFamiliesAdminAssessmentGeneratePost,
} from "@/api/endpoints/admin/admin";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { FamilyOrderInKind, FamilyOrderOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { KINDS } from "./model";
import { T } from "./text";

/** E43-9: заказ LLM-заданий из «Допуска заданий» — кнопка с формой и список последних заказов. */

const sel = (s: string) => `gen-${s}`;
const ACTIVE = new Set(["queued", "running"]);
const MAX = 10;

function useOrders() {
  const q = useFamilyOrdersAdminAssessmentGenerateGet({
    query: {
      retry: false,
      // пока заказ в очереди или идёт — обновляем статус раз в 3 с
      refetchInterval: (query) => {
        const d = query.state.data;
        return d?.status === 200 && d.data.items.some((o) => ACTIVE.has(o.status)) ? 3000 : false;
      },
    },
  });
  return q.data?.status === 200 ? q.data.data : null;
}

function problemText(err: unknown): string {
  if (err instanceof ApiError && err.code && T.gen.problem[err.code]) return T.gen.problem[err.code]!;
  return T.gen.submitError;
}

/** Кнопка «Сгенерировать задания» и модалка формы (навык с поиском, тип, уровень, количество). */
export function GenerateButton() {
  const qc = useQueryClient();
  const data = useOrders();
  const [open, setOpen] = useState(false);
  const [skill, setSkill] = useState<string | null>(null);
  const [kind, setKind] = useState<FamilyOrderInKind>("exact");
  const [level, setLevel] = useState(3);
  const [count, setCount] = useState<number | null>(3);
  const [err, setErr] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const taxonomy = useGetTaxonomyTaxonomyGet({ query: { enabled: open } });
  const skills = useMemo(
    () => (taxonomy.data?.data as { skills?: { slug: string; name: string }[] } | undefined)?.skills ?? [],
    [taxonomy.data],
  );
  const max = data?.max_count ?? MAX;
  const over = data ? data.used_today >= data.limit : false;

  const order = useGenerateFamiliesAdminAssessmentGeneratePost({
    mutation: {
      onSuccess: (res) => {
        if (res.status !== 202) return;
        setErr(null);
        setNote(res.data.duplicate ? T.gen.duplicateNote : T.gen.queuedNote);
        void qc.invalidateQueries({ queryKey: getFamilyOrdersAdminAssessmentGenerateGetQueryKey() });
        setOpen(false);
      },
      onError: (e) => setErr(problemText(e)),
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!skill) {
      setErr(T.gen.needSkill);
      return;
    }
    if (order.isPending) return; // второй клик, пока первый в пути
    setErr(null);
    order.mutate({ data: { skill, kind, level, count: Math.min(max, Math.max(1, count ?? 1)) } });
  };

  // черновики обновятся, когда заказ дойдёт до «Готово»
  const done = data?.items.filter((o) => o.status === "done").length ?? 0;
  useEffect(() => {
    if (done > 0) void qc.invalidateQueries({ queryKey: getAdmissionQueueAdminFamiliesGetQueryKey().slice(0, 1) });
  }, [done, qc]);

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <Button type="button" data-testid={sel("open")} onClick={() => { setErr(null); setNote(null); setOpen(true); }}>
        {T.gen.open}
      </Button>
      {note && (
        <p className="max-w-xs text-12 text-muted sm:text-right" data-testid={sel("note")} role="status">
          {note}
        </p>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid={sel("dialog")}>
          <DialogTitle>{T.gen.title}</DialogTitle>
          <DialogDescription>{T.gen.lead}</DialogDescription>
          <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-4" data-testid={sel("form")}>
            <Field label={T.gen.skill} hint={T.gen.skillHint}>
              <Combobox
                data-testid={sel("skill")}
                value={skill}
                onChange={(v) => setSkill(v)}
                options={skills.map((s) => ({ value: s.slug, label: s.name, hint: s.slug }))}
                placeholder={T.gen.skillPlaceholder}
                limit={50}
              />
            </Field>
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-14 font-semibold">{T.gen.kind}</legend>
              <div role="radiogroup" aria-label={T.gen.kind} className="flex flex-wrap gap-2">
                {KINDS.map((k) => (
                  <button
                    key={k}
                    type="button"
                    role="radio"
                    aria-checked={kind === k}
                    data-testid={sel(`kind-${k}`)}
                    onClick={() => setKind(k as FamilyOrderInKind)}
                    className={cn(
                      "min-h-9 rounded-lg border px-3 text-13 font-semibold",
                      kind === k ? "border-brand bg-brand text-on-brand" : "border-hairline bg-card hover:bg-tint-50",
                    )}
                  >
                    {T.builder.kindLabel[k] ?? k}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={T.gen.level}>
                <Select
                  data-testid={sel("level")}
                  value={String(level)}
                  onChange={(v) => v && setLevel(Number(v))}
                  options={[1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: T.gen.levelOption(n) }))}
                />
              </Field>
              <Field label={T.gen.count} hint={T.gen.countHint(max)}>
                <NumberInput data-testid={sel("count")} value={count} onChange={setCount} min={1} max={max} />
              </Field>
            </div>
            {data && (
              <p className={cn("text-13", over ? "text-error" : "text-muted")} data-testid={sel("quota")}>
                {over ? T.gen.quotaOver : T.gen.quota(data.used_today, data.limit)}
              </p>
            )}
            {err && (
              <p role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
                {err}
              </p>
            )}
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
                {T.gen.cancel}
              </Button>
              <Button type="submit" data-testid={sel("submit")} disabled={order.isPending || over}>
                {T.gen.submit}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function statusVariant(s: string): "muted" | "warning" | "success" | "error" {
  return s === "done" ? "success" : s === "failed" ? "error" : s === "running" ? "warning" : "muted";
}

function OrderRow({ o, skillName, onDrafts }: { o: FamilyOrderOut; skillName: string; onDrafts?: () => void }) {
  const rejected = Object.entries(o.rejected ?? {}).filter(([, n]) => n > 0);
  return (
    <li className="flex min-w-0 flex-col gap-1 rounded-lg border border-hairline px-3 py-2" data-testid={sel(`order-${o.id}`)} data-status={o.status}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 truncate text-14 font-semibold">{skillName}</span>
        <Badge variant="muted">{T.builder.kindLabel[o.kind] ?? o.kind}</Badge>
        <Badge variant="muted">{T.gen.levelOption(o.level)}</Badge>
        <Badge variant={statusVariant(o.status)} className="ml-auto" data-testid={sel(`status-${o.id}`)}>
          {T.gen.status[o.status] ?? o.status}
        </Badge>
      </div>
      <p className="text-13 text-muted" data-testid={sel(`count-${o.id}`)}>
        {o.status === "failed"
          ? (o.error && T.gen.errors[o.error]) || T.gen.errorDefault
          : T.gen.result(o.created ?? 0, o.count)}
        {rejected.length > 0 && ` · ${T.gen.rejected}: ${rejected.map(([r, n]) => `${T.gen.reasons[r] ?? r} ${n}`).join(", ")}`}
      </p>
      {o.status === "done" && (o.created ?? 0) > 0 && onDrafts && (
        <button type="button" onClick={onDrafts} className="self-start text-13 font-semibold text-brand-deep underline-offset-2 hover:underline dark:text-brand-mid" data-testid={sel(`drafts-${o.id}`)}>
          {T.gen.toDrafts}
        </button>
      )}
    </li>
  );
}

/** Последние заказы: статус (в очереди / идёт / готово / ошибка) и счётчик черновиков. */
export function OrdersPanel({ onDrafts }: { onDrafts?: () => void }) {
  const data = useOrders();
  const taxonomy = useGetTaxonomyTaxonomyGet({ query: { enabled: (data?.items.length ?? 0) > 0 } });
  const names = useMemo(() => {
    const list = (taxonomy.data?.data as { skills?: { slug: string; name: string }[] } | undefined)?.skills ?? [];
    return new Map(list.map((s) => [s.slug, s.name]));
  }, [taxonomy.data]);
  if (!data || data.items.length === 0) return null;
  const items = data.items.slice(0, 6);
  return (
    <section aria-label={T.gen.orders} className="flex flex-col gap-2" data-testid={sel("orders")}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-16 font-semibold">{T.gen.orders}</h2>
        <span className="text-13 text-muted" data-testid={sel("orders-quota")}>
          {T.gen.quota(data.used_today, data.limit)}
        </span>
      </div>
      <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {items.map((o) => (
          <OrderRow key={o.id} o={o} skillName={names.get(o.skill) ?? o.skill} onDrafts={onDrafts} />
        ))}
      </ul>
    </section>
  );
}
