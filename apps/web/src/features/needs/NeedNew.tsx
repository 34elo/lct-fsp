import { PAGE } from "@/shared/lib/page";
import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Button, SectionLabel, cn } from "@fsp/ui";

import { useCreateNeedNeedsPost } from "@/api/endpoints/needs/needs";
import { ApiError } from "@/api/mutator";
import { NEED_TEXT as T } from "./text";

/** Потребность текстом (состояние «ввод» и «ошибка разбора»). */
export default function NeedNew() {
  const navigate = useNavigate();
  const id = useId();
  const [text, setText] = useState("");
  const [error, setError] = useState<{ empty: boolean } | null>(null);
  const create = useCreateNeedNeedsPost();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    setError(null);
    create.mutate(
      { data: { text: t } },
      {
        onSuccess: (r) => {
          if (r.status === 201) navigate(`/employer/needs/${r.data.id}`, { state: { need: r.data } });
        },
        onError: (err) => setError({ empty: err instanceof ApiError && err.code === "need_empty" }),
      },
    );
  };

  return (
    <div className={cn(PAGE.narrow, "gap-6")}>
      <header className="grid gap-2">
        <SectionLabel>{T.kicker}</SectionLabel>
        <h1 className="font-mono text-24 font-semibold">{T.title}</h1>
        <p className="text-14 text-muted">{T.lead}</p>
      </header>

      <form onSubmit={submit} className="grid gap-3">
        <label htmlFor={id} className="font-mono text-13 font-semibold">
          {T.label}
        </label>
        <textarea
          id={id}
          value={text}
          maxLength={500}
          rows={3}
          onChange={(e) => setText(e.target.value)}
          placeholder={T.placeholder}
          aria-invalid={error ? true : undefined}
          className="min-h-24 w-full rounded-lg border border-brand-mid bg-card p-4 text-16 text-ink placeholder:text-muted focus:border-brand focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="lg" loading={create.isPending} disabled={!text.trim()}>
            {T.submit}
          </Button>
          <span className="text-12 text-muted">{T.local}</span>
        </div>
      </form>

      {error && (
        <div role="alert" className="grid gap-2 rounded-xl border border-error p-4">
          <p className="font-mono text-15 font-semibold">{T.failed}</p>
          <p className="text-13 text-muted">{T.failedHint}</p>
          <Link to="/employer/search" className="w-fit font-semibold text-brand-fg hover:underline">
            {T.openForm}
          </Link>
        </div>
      )}
    </div>
  );
}
