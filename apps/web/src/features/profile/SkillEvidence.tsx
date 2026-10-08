import { PAGE } from "@/shared/lib/page";
import { Link, useParams } from "react-router-dom";

import { useSkillEvidenceCandidatesMeSkillsSkillIdEvidenceGet } from "@/api/endpoints/candidates/candidates";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { dateRu, SOURCE_LABEL } from "@/features/profile/text";

/** «Откуда взялся навык»: доказательства навыка владельца, свежие первыми. */
export default function SkillEvidence() {
  const { slug = "" } = useParams();
  const q = useSkillEvidenceCandidatesMeSkillsSkillIdEvidenceGet(slug, { query: { retry: false } });
  let body: React.ReactNode;
  if (q.isPending) body = <p role="status" className="text-muted">Загрузка…</p>;
  else if (q.isError || q.data.status !== 200) {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    body = <ErrorNote>{notFound ? "Такого навыка нет в вашем профиле." : "Не удалось загрузить доказательства."}</ErrorNote>;
  } else if (q.data.data.length === 0) {
    body = <p className="text-sm text-muted">Доказательств пока нет: навык заявлен или выведен. Подтвердите его тестом или результатом ФСП.</p>;
  } else {
    body = (
      <ul className="flex flex-col">
        {q.data.data.map((e) => (
          <li key={e.id} className="flex flex-col gap-1 border-t border-hairline py-3 first:border-t-0">
            <span className="font-medium">{e.title}</span>
            <span className="flex flex-wrap items-center gap-x-3 text-[13px] text-muted">
              <span className="font-mono">{SOURCE_LABEL[e.source] ?? e.source}</span>
              <span>{dateRu(e.observed_at)}</span>
              <span>{e.verified ? "проверено" : "не проверено"}</span>
              <span className="font-mono">сила {Math.round(e.strength * 100)}%</span>
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className={PAGE.narrow}>
      <Link to="/me/profile" className="inline-flex min-h-11 items-center font-semibold text-brand-fg">
        ← Профиль
      </Link>
      <section className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-5">
        <h1 className="font-mono text-xl font-semibold">Чем подтверждён навык</h1>
        {body}
      </section>
    </div>
  );
}
