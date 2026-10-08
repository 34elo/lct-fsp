import { Link, useLocation } from "react-router-dom";

import { LEGAL_PAGES } from "./legal-text";

/** Статичные «Условия» и «Приватность»: публичные, без входа (E35-7b). */
export default function Legal() {
  const { pathname } = useLocation();
  const page = pathname === "/privacy" ? LEGAL_PAGES.privacy : LEGAL_PAGES.terms;
  return (
    <article className="mx-auto flex max-w-2xl flex-col gap-4 py-2">
      <h1 className="text-2xl font-semibold">{page.title}</h1>
      {page.paragraphs.map((p) => (
        <p key={p} className="text-14 text-muted">
          {p}
        </p>
      ))}
      <Link to="/" className="font-semibold text-brand-fg">
        На главную
      </Link>
    </article>
  );
}
