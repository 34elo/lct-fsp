import { useNavigate } from "react-router-dom";

import { Roadmap, SectionLabel, type RoadmapAction, type RoadmapStep } from "@fsp/ui";

import type { NavCompetition, NavigatorOut, UpliftItem } from "@/api/model";
import { GRADE_LABEL } from "@/features/profile/text";
import { T } from "./text";

const dateShort = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" });

const TASKS_PATH = "/me/tasks";

/** Этапы роадмапа: текущий грейд → навыки-пробелы → тест → следующий грейд. Чистая функция для тестов. */
export function roadmapSteps(nav: NavigatorOut, uplift: UpliftItem[] = nav.uplift): RoadmapStep[] {
  const steps: RoadmapStep[] = [];
  const cur = nav.current_grade;
  const testPath = nav.test?.path;
  const retake: RoadmapAction[] = cur?.needs_confirmation && testPath ? [{ label: T.retake, href: testPath }] : [];
  steps.push({
    id: "current",
    kind: "current",
    state: "done",
    eyebrow: T.stepNow,
    title: cur ? (GRADE_LABEL[cur.grade] ?? cur.grade) : "—",
    caption: cur ? (cur.needs_confirmation ? T.expired : T.validUntil(dateShort(cur.valid_until))) : undefined,
    actions: retake,
  });
  nav.skill_gaps.forEach((g, i) => {
    const up = uplift.find((u) => u.skill === g.skill);
    const actions: RoadmapAction[] = [{ label: T.doTask, href: TASKS_PATH }];
    steps.push({
      id: `gap-${g.skill}`,
      kind: "skill",
      state: i === 0 ? "current" : "future",
      eyebrow: T.stepSkill,
      title: g.name,
      uplift: up ? T.upliftChip(Math.round(up.pct)) : undefined,
      caption: T.gapCaption,
      actions,
    });
  });
  if (testPath) {
    steps.push({
      id: "test",
      kind: "test",
      state: "future",
      eyebrow: T.stepTest,
      title: T.testTitle,
      caption: nav.test ? T.testLead(GRADE_LABEL[nav.test.grade] ?? nav.test.grade) : undefined,
      actions: [{ label: T.takeTest, href: testPath }],
    });
  }
  const goal = nav.target?.grade ?? nav.test?.grade;
  if (goal) {
    steps.push({
      id: "next",
      kind: "goal",
      state: "future",
      eyebrow: T.stepGoal,
      title: GRADE_LABEL[goal] ?? goal,
      caption: nav.next_grade ? T.pointsNeeded(nav.next_grade.points_needed) : undefined,
    });
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

/** Роадмап от текущего грейда к следующему; ниже подсказки и список соревнований ФСП. */
export function NavigatorPath({ nav, uplift }: { nav: NavigatorOut; uplift?: UpliftItem[] }) {
  const go = useNavigate();
  const steps = roadmapSteps(nav, uplift).map((st) => ({
    ...st,
    actions: st.actions?.map((a) => (a.external ? a : { ...a, onClick: () => go(a.href) })),
  }));
  return (
    <section aria-labelledby="nav-path" className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4">
      <SectionLabel id="nav-path">{T.pathTitle}</SectionLabel>
      <Roadmap steps={steps} label={T.roadmapLabel} />
      {nav.next_grade && nav.next_grade.hints.length > 0 && (
        <p className="text-14 text-muted">{nav.next_grade.hints.join(". ")}</p>
      )}
      <div className="flex flex-col gap-2">
        <h3 className="text-14 font-semibold">{T.competitionsTitle}</h3>
        {nav.competitions.length === 0 ? (
          <p className="text-13 text-muted">{T.noCompetitions}</p>
        ) : (
          <>
            <p className="text-13 text-muted">{T.competitionsLead}</p>
            <ul className="m-0 flex list-none flex-col gap-2 p-0">
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
