import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  getGetRunPublicRunTokenGetQueryKey,
  useGetRunPublicRunTokenGet,
  useStartRunRunTokenStartPost,
} from "@/api/endpoints/live-runs/live-runs";
import { Button } from "@fsp/ui";
import { ErrorNote } from "@/features/auth/ui";
import { SusForm } from "@/features/runs/SusForm";
import { runError, T } from "@/features/runs/text";
import { setRunId } from "@/shared/lib/track";

const POLL_MS = 4000;

/**
 * `/run/:token` — экран испытателя: задания засчитываются сами по событиям,
 * в конце анкета SUS. Метка прогона ставится на все события интерфейса вкладки.
 */
export default function RunPage() {
  const { token = "" } = useParams();
  const qc = useQueryClient();
  const [sent, setSent] = useState(false);
  const [wantSus, setWantSus] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const start = useStartRunRunTokenStartPost();
  const state = useGetRunPublicRunTokenGet(token, {
    query: {
      retry: false,
      refetchInterval: (q) => (q.state.data?.status === 200 && q.state.data.data.status === "finished" ? false : POLL_MS),
    },
  });

  const run = state.data?.status === 200 ? state.data.data : undefined;
  const id = run?.id;
  const status = run?.status;

  useEffect(() => {
    if (id) setRunId(status === "finished" ? null : id);
  }, [id, status]);

  const refresh = () => qc.invalidateQueries({ queryKey: getGetRunPublicRunTokenGetQueryKey(token) });

  async function begin() {
    setError(null);
    try {
      await start.mutateAsync({ token });
      await refresh();
    } catch (e) {
      setError(runError(e));
    }
  }

  if (state.isPending) return <p role="status" className="p-6 text-muted">{T.loading}</p>;
  if (!run) return <ErrorNote className="mx-auto mt-6 max-w-lg">{T.notFound}</ErrorNote>;

  const finished = run.status === "finished";
  const showSus = !finished && (wantSus || (run.all_done && run.status === "started"));

  return (
    <section className="mx-auto flex w-full max-w-lg flex-col gap-5 p-4 md:py-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold">{T.title}</h1>
        {!finished && <p className="text-sm text-muted">{T.lead}</p>}
      </header>

      {finished && (
        <p role="status" className="rounded-lg border border-hairline bg-card p-4 text-sm">
          {sent ? T.thanks : T.finished}
        </p>
      )}

      {!finished && (
        <>
          <h2 className="text-lg font-semibold">{T.tasks}</h2>
          <ol className="flex flex-col gap-2">
            {run.tasks.map((t) => (
              <li
                key={t.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-hairline bg-card p-3 text-sm"
              >
                <span className={t.done ? "text-muted line-through" : ""}>{t.title}</span>
                <span className="shrink-0 text-xs font-semibold">
                  {t.done ? T.done : t.target > 1 ? T.progress(t.count, t.target) : ""}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}

      {run.status === "invited" && (
        <Button onClick={() => void begin()} disabled={start.isPending}>
          {start.isPending ? T.starting : T.start}
        </Button>
      )}

      {run.status === "started" && !showSus && (
        <div className="flex flex-col gap-3">
          <Link
            to="/register"
            className="inline-flex h-11 items-center justify-center rounded-lg bg-ink px-4 text-sm font-semibold text-card"
          >
            {T.open}
          </Link>
          <p className="text-xs text-muted">{T.openHint}</p>
          <Button variant="outline" onClick={() => setWantSus(true)}>
            {T.finish}
          </Button>
        </div>
      )}

      {showSus && (
        <>
          {run.all_done && <p className="text-sm font-medium">{T.allDone}</p>}
          <SusForm
            token={token}
            onDone={() => {
              setSent(true);
              setRunId(null);
              void refresh();
            }}
          />
        </>
      )}
    </section>
  );
}
