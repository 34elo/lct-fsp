import { Button, buttonVariants, CircuitLine, SectionLabel, type CircuitStep } from "@fsp/ui";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";
import { ResumeStep } from "@/features/onboarding/ResumeStep";
import { ONBOARDING, STEPS, skillsStatus, type StepId } from "@/features/onboarding/text";

type Outcome = "done" | "skipped";

/**
 * Онбординг кандидата (макет M1): вертикальная схемная линия и один шаг на экран, любой шаг можно пропустить.
 * Согласие `pd_processing` уже выдано: без него `RequireRole` не пускает в кабинет.
 */
export default function Onboarding() {
  const [params] = useSearchParams();
  // Возврат из ФСП (?fsp=linked|error): сразу на шаг «ФСП», пройденные до него шаги считаем закрытыми.
  const fromFsp = params.get("fsp") !== null;
  const [index, setIndex] = useState(fromFsp ? 2 : 1);
  const [outcome, setOutcome] = useState<Partial<Record<StepId, Outcome>>>({ consents: "done" });
  const [skills, setSkills] = useState<number | null>(null);

  const finish = (id: StepId, o: Outcome) => {
    setOutcome((s) => ({ ...s, [id]: o }));
    setIndex((i) => Math.min(i + 1, STEPS.length - 1));
  };

  const circuit: CircuitStep[] = STEPS.map((s, i) => {
    const state: CircuitStep["state"] = i < index ? "done" : i === index ? "current" : "future";
    let status = "";
    if (state === "done") {
      status =
        outcome[s.id] === "skipped"
          ? ONBOARDING.statusSkipped
          : s.id === "resume" && skills !== null
            ? skillsStatus(skills)
            : ONBOARDING.statusDone;
    }
    return { id: s.id, label: status ? `${s.title} · ${status}` : s.title, state };
  });

  const step = STEPS[index];

  return (
    <section data-testid="onboarding-root" className="mx-auto flex w-full max-w-3xl flex-col gap-6 py-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{ONBOARDING.title}</h1>
        <p className="text-14 text-muted">
          Шаг {index + 1} из {STEPS.length} · {ONBOARDING.eta}. {ONBOARDING.skipHint}
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-[220px_1fr]">
        <CircuitLine steps={circuit} />

        <div
          data-testid={`onboarding-step-${step.id}`}
          className="flex min-w-0 flex-col gap-4 rounded-2xl border border-hairline bg-card p-4 md:p-6"
        >
          <header className="flex flex-col gap-1">
            <SectionLabel>
              {index + 1} · {step.title}
            </SectionLabel>
            <h2 className="text-20 font-semibold">{step.title}</h2>
            {step.id !== "resume" && <p className="text-14 text-muted">{step.lead}</p>}
          </header>

          {step.id === "resume" && (
            <ResumeStep
              onDone={(n) => {
                setSkills(n);
                finish("resume", "done");
              }}
              onSkip={() => finish("resume", "skipped")}
            />
          )}

          {step.id === "fsp" && (
            <div className="flex flex-col gap-3">
              <FspLinkPanel next="/onboarding" onLinked={() => finish("fsp", "done")} />
              <Button variant="ghost" data-testid="onboarding-skip" onClick={() => finish("fsp", "skipped")}>
                {params.get("fsp") === "linked" ? ONBOARDING.next : ONBOARDING.skip}
              </Button>
            </div>
          )}

          {step.id === "done" && (
            <div className="flex flex-col gap-3">
              <p className="text-14 text-muted">
                {outcome.resume === "done" ? ONBOARDING.doneWithResume : ONBOARDING.doneNoResume}
              </p>
              <Link
                to="/me"
                data-testid="onboarding-to-profile"
                className={buttonVariants({ size: "lg" })}
              >
                {ONBOARDING.toProfile}
              </Link>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
