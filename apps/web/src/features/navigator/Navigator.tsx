import { PAGE } from "@/shared/lib/page";
import { Link, useNavigate } from "react-router-dom";

import { buttonVariants, EmptyState, ErrorState, formatRub, SectionLabel, Skeleton, UpliftCard } from "@fsp/ui";

import { useMyNavigatorCandidatesMeNavigatorGet, useMyUpliftCandidatesMeUpliftGet } from "@/api/endpoints/search/search";
import type { NavigatorOut, UpliftItem, UpliftOut } from "@/api/model";
import { UpliftConfirmKind } from "@/api/model";
import { GRADE_LABEL } from "@/features/profile/text";
import { NavigatorPath } from "./NavigatorPath";
import { confirmHint, errorText, T } from "./text";

const dateShort = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });

/** Карточка роста: прирост числа вакансий и способы подтвердить навык. */
export function UpliftItemCard({ item, testPath }: { item: UpliftItem; testPath?: string }) {
  const go = useNavigate();
  const canTest = item.how_to_confirm.some((c) => c.kind === UpliftConfirmKind.test) && !!testPath;
  const extra = [T.extra(item.extra), item.median_salary_delta > 0 ? T.salaryDelta(formatRub(item.median_salary_delta)) : ""]
    .filter(Boolean)
    .join(", ");
  return (
    <li>
      <UpliftCard
        skill={item.name}
        pct={Math.round(item.pct)}
        hint={[extra, confirmHint(item.how_to_confirm, dateShort)].filter(Boolean).join(". ")}
        actionLabel={T.takeTest}
        onConfirm={canTest ? () => go(testPath!) : undefined}
      />
    </li>
  );
}

export function UpliftList({ uplift, testPath }: { uplift: UpliftOut; testPath?: string }) {
  return (
    <section aria-labelledby="nav-uplift" className="flex flex-col gap-3">
      <SectionLabel id="nav-uplift">{T.upliftTitle}</SectionLabel>
      {uplift.relevant_total > 0 && <p className="text-13 text-muted">{T.upliftLead(uplift.relevant_total)}</p>}
      <ul className="grid gap-3 sm:grid-cols-2">
        {uplift.items.map((it) => (
          <UpliftItemCard key={it.skill} item={it} testPath={testPath} />
        ))}
      </ul>
      {uplift.combo && (
        <p className="rounded-lg bg-tint-50 p-3 text-14">
          {T.combo(uplift.combo.skills.join(" + "), Math.round(uplift.combo.pct))}
        </p>
      )}
    </section>
  );
}

function empty(nav: NavigatorOut, up?: UpliftOut) {
  return !nav.current_grade && !nav.target && nav.skill_gaps.length === 0 && nav.competitions.length === 0 && !(up?.items.length ?? nav.uplift.length);
}

export default function Navigator() {
  const navQ = useMyNavigatorCandidatesMeNavigatorGet();
  const upQ = useMyUpliftCandidatesMeUpliftGet();
  const navData = navQ.data?.status === 200 ? navQ.data.data : undefined;
  const upData = upQ.data?.status === 200 ? upQ.data.data : undefined;
  // Если отдельный запрос не удался, берём список из навигатора.
  const uplift: UpliftOut | null =
    upData ?? (navData?.uplift.length ? { relevant_total: 0, base: 0, items: navData.uplift, combo: null } : null);

  return (
    <div className={PAGE.narrow}>
      <header>
        <h1 className="font-mono text-2xl font-semibold">{T.title}</h1>
        <p className="text-14 text-muted">{T.lead}</p>
      </header>
      {navQ.isPending ? (
        <div role="status" aria-label={T.loading} className="flex flex-col gap-3">
          <Skeleton className="h-40" />
          <Skeleton className="h-28" />
        </div>
      ) : navQ.isError || !navData ? (
        <ErrorState title={errorText(navQ.error)} onRetry={() => navQ.refetch()} />
      ) : empty(navData, upData) ? (
        <EmptyState
          title={T.emptyTitle}
          description={T.emptyText}
          action={
            <Link to="/me/assessment" className={buttonVariants()}>
              {T.emptyAction}
            </Link>
          }
        />
      ) : (
        <>
          <NavigatorPath nav={navData} />
          {navData.test && (
            <section className="flex flex-col gap-2 rounded-xl border border-brand bg-card p-4">
              <p className="text-14">{T.testLead(GRADE_LABEL[navData.test.grade] ?? navData.test.grade)}</p>
              <Link
                to={navData.test.path}
                className={`${buttonVariants()} self-start`}
              >
                {T.takeTest}
              </Link>
            </section>
          )}
          {uplift && <UpliftList uplift={uplift} testPath={navData.test?.path} />}
        </>
      )}
    </div>
  );
}
