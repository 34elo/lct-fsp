import { useQueryClient } from "@tanstack/react-query";

import { problemText } from "./model";
import { SK } from "./text";

/** Любая правка графа меняет все списки раздела: сбрасываем их разом. */
export function useRefreshSkills() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0] ?? "").startsWith("/admin/skills") });
}

export const skErr = (e: unknown) => problemText(e, SK.problem, SK.actionError);

export const shortDate = (iso: string) => iso.slice(0, 10).split("-").reverse().join(".");

export function Notice({ ok, err }: { ok: string; err: string | null }) {
  return (
    <>
      {ok && <p role="status" data-testid="admin-sk-notice" className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success-fg">{ok}</p>}
      {err && <p role="alert" data-testid="admin-sk-error" className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">{err}</p>}
    </>
  );
}
