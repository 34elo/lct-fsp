import { useLocation } from "react-router-dom";

import { ROUTES } from "@/app/routes";

/** Раздел, который ещё не реализован: понятная заглушка вместо технического вывода. */
export function Stub({ routePath }: { routePath: string }) {
  const def = ROUTES.find((r) => r.path === routePath);
  const { pathname } = useLocation();
  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-2 rounded-xl border border-dashed border-hairline bg-card p-6">
      <h1 className="font-mono text-2xl font-semibold">{def?.title ?? pathname}</h1>
      <p className="text-sm text-muted">Раздел готовится и появится в следующих версиях.</p>
    </section>
  );
}
