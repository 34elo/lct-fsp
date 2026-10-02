import { useLocation, useParams } from "react-router-dom";

import { ROUTES } from "@/app/routes";

/** Пустая страница раздела: заголовок и ссылка на макет. Заменяется задачами E3-5, E4-7 и др. */
export function Stub({ routePath }: { routePath: string }) {
  const def = ROUTES.find((r) => r.path === routePath);
  const params = useParams();
  const { pathname } = useLocation();
  return (
    <section className="flex flex-col gap-3">
      <h1 className="text-2xl font-bold">{def?.title ?? pathname}</h1>
      <p className="font-mono text-sm text-muted">
        {routePath}
        {def?.screen ? ` · макет ${def.screen}` : ""}
      </p>
      {Object.keys(params).length > 0 && <p className="font-mono text-xs text-muted">{JSON.stringify(params)}</p>}
    </section>
  );
}
