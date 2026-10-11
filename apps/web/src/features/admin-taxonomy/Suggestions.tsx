import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge, Button, ErrorState, InfoTip, Skeleton } from "@fsp/ui";

import {
  getListProfessionSuggestionsAdminProfessionSuggestionsGetQueryKey,
  getListProfessionsAdminProfessionsGetQueryKey,
  useAcceptProfessionSuggestionAdminProfessionSuggestionsSuggestionIdAcceptPost,
  useListProfessionSuggestionsAdminProfessionSuggestionsGet,
  useRejectProfessionSuggestionAdminProfessionSuggestionsSuggestionIdRejectPost,
} from "@/api/endpoints/admin/admin";
import type { ProfessionSuggestionOut } from "@/api/model";
import { problemText } from "./model";
import { T } from "./text";

const sel = (s: string) => `admin-sugg-${s}`;

function SuggestionCard({ s, onDone }: { s: ProfessionSuggestionOut; onDone: (msg: string) => void }) {
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: getListProfessionSuggestionsAdminProfessionSuggestionsGetQueryKey() });
    void qc.invalidateQueries({ queryKey: getListProfessionsAdminProfessionsGetQueryKey() });
  };
  const opts = (msg: string) => ({
    mutation: {
      onSuccess: () => {
        refresh();
        onDone(msg);
      },
      onError: (e: unknown) => setErr(problemText(e, T.sugg.problem, T.sugg.error)),
    },
  });
  const accept = useAcceptProfessionSuggestionAdminProfessionSuggestionsSuggestionIdAcceptPost(opts(T.sugg.created(s.title)));
  const reject = useRejectProfessionSuggestionAdminProfessionSuggestionsSuggestionIdRejectPost(opts(T.sugg.rejected(s.title)));
  const busy = accept.isPending || reject.isPending;

  return (
    <li className="flex h-full flex-col gap-3 rounded-xl border border-tint-200 bg-card p-4" data-testid={sel(`card-${s.id}`)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="text-16 font-semibold" data-testid={sel("title")}>{s.title}</h3>
        <Badge variant="dashed">{T.sugg.badge}</Badge>
      </div>
      <p className="text-13 text-muted">{T.sugg.support(s.support_vacancies, s.support_needs)}</p>
      <div className="flex flex-col gap-1">
        <span className="text-13 font-semibold">{T.sugg.core}</span>
        <ul className="flex flex-wrap gap-1" aria-label={T.sugg.core}>
          {s.skills.map((k) => (
            <li key={k.slug}>
              <Badge variant="muted" title={k.slug}>{k.name}</Badge>
            </li>
          ))}
        </ul>
      </div>
      <p className="text-13" data-testid={sel("nearest")}>
        {s.nearest ? T.sugg.nearest(s.nearest.title, Math.round(s.nearest.overlap * 100)) : T.sugg.noNearest}
      </p>
      {s.examples.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-13 font-semibold">{T.sugg.examples}</span>
          <ul className="list-disc pl-5 text-13 text-muted">
            {s.examples.map((e, i) => (
              <li key={e.vacancy_id ?? i} className="break-words">{e.title}</li>
            ))}
          </ul>
        </div>
      )}
      {err && (
        <p role="alert" data-testid={sel("error")} className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">{err}</p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-2">
        <Button type="button" disabled={busy} data-testid={sel("create")} onClick={() => { setErr(null); accept.mutate({ suggestionId: s.id, data: {} }); }}>
          {T.sugg.create}
        </Button>
        <Button type="button" variant="ghost" disabled={busy} title={T.sugg.rejectHint} data-testid={sel("reject")} onClick={() => { setErr(null); reject.mutate({ suggestionId: s.id }); }}>
          {T.sugg.reject}
        </Button>
      </div>
    </li>
  );
}

/** «Новая профессия?»: предложения системы, создание одной кнопкой или отказ. */
export function ProfessionSuggestions({ onDone }: { onDone: (msg: string) => void }) {
  const q = useListProfessionSuggestionsAdminProfessionSuggestionsGet({ query: { retry: false } });
  const items = q.data?.status === 200 ? q.data.data : null;

  return (
    <section className="flex flex-col gap-3" data-testid={sel("section")} aria-labelledby={sel("heading")}>
      <h2 id={sel("heading")} className="flex items-center gap-2 text-18 font-semibold">
        {T.sugg.title}
        <InfoTip label={T.sugg.title}>{T.sugg.tip}</InfoTip>
      </h2>
      {q.isLoading && <Skeleton className="h-24" />}
      {(q.isError || (q.data && q.data.status !== 200)) && <ErrorState description={T.loadError} onRetry={() => void q.refetch()} />}
      {items && items.length === 0 && (
        <p className="text-13 text-muted" data-testid={sel("empty")}>{T.sugg.empty}</p>
      )}
      {items && items.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid={sel("list")}>
          {items.map((s) => (
            <SuggestionCard key={s.id} s={s} onDone={onDone} />
          ))}
        </ul>
      )}
    </section>
  );
}
