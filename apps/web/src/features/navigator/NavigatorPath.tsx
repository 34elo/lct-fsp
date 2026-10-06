import { CircuitLine, SectionLabel, type CircuitStep } from "@fsp/ui";

import type { NavCompetition, NavigatorOut } from "@/api/model";
import { GRADE_LABEL } from "@/features/profile/text";
import { T } from "./text";

const dateShort = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });

/** Узлы схемы: текущий грейд, навыки-пробелы, целевой грейд. Чистая функция для тестов. */
export function pathSteps(nav: NavigatorOut): CircuitStep[] {
  const steps: CircuitStep[] = [];
  const cur = nav.current_grade;
  steps.push({
    id: "current",
    state: "done",
    label: cur ? T.current(GRADE_LABEL[cur.grade] ?? cur.grade) : T.current("—"),
  });
  nav.skill_gaps.forEach((g, i) =>
    steps.push({ id: `gap-${g.skill}`, state: i === 0 ? "current" : "future", label: g.name }),
  );
  if (nav.target?.grade || nav.test?.grade) {
    const grade = nav.target?.grade ?? nav.test!.grade;
    steps.push({ id: "next", state: "future", label: T.nextGrade(GRADE_LABEL[grade] ?? grade) });
  }
  return steps;
}

function Flag({ c }: { c: NavCompetition }) {
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-hairline bg-card p-3">
      <span className="flex items-baseline justify-between gap-2">
        <b className="text-14">{c.title}</b>
        <span className="shrink-0 font-mono text-13 text-muted">{T.startsOn(dateShort(c.start_date))}</span>
      </span>
      {c.skills.length > 0 && <span className="text-13 text-muted">{T.skills(c.skills)}</span>}
      {c.registration_url && (
        <a
          href={c.registration_url}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex h-11 items-center self-start text-14 font-semibold text-brand-fg underline-offset-4 hover:underline"
        >
          {T.register}
        </a>
      )}
    </li>
  );
}

/** Схемная линия от текущего грейда к следующему: узлы — навыки, флажки — соревнования ФСП. */
export function NavigatorPath({ nav }: { nav: NavigatorOut }) {
  const steps = pathSteps(nav);
  const cur = nav.current_grade;
  return (
    <section aria-labelledby="nav-path" className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4">
      <SectionLabel id="nav-path">{T.pathTitle}</SectionLabel>
      <CircuitLine steps={steps} />
      {nav.next_grade && (
        <p className="text-14">
          {T.pointsNeeded(nav.next_grade.points_needed)}
          {nav.next_grade.hints.length > 0 && <span className="text-muted">{`. ${nav.next_grade.hints.join(". ")}`}</span>}
        </p>
      )}
      {cur && (
        <p className="text-13 text-muted">
          {cur.needs_confirmation ? T.expired : T.validUntil(dateShort(cur.valid_until))}
        </p>
      )}
      <div className="flex flex-col gap-2">
        <h3 className="text-14 font-semibold">{T.competitionsTitle}</h3>
        {nav.competitions.length === 0 ? (
          <p className="text-13 text-muted">{T.noCompetitions}</p>
        ) : (
          <>
            <p className="text-13 text-muted">{T.competitionsLead}</p>
            <ul className="flex flex-col gap-2">
              {nav.competitions.map((c) => (
                <Flag key={c.id} c={c} />
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
