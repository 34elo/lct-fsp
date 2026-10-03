import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";

import { ResumeStep } from "@/features/onboarding/ResumeStep";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/button";

type StepId = "consents" | "resume" | "fsp" | "github" | "done";
type Outcome = "done" | "skipped";

const STEPS: { id: StepId; title: string }[] = [
  { id: "consents", title: "Согласия" },
  { id: "resume", title: "Резюме" },
  { id: "fsp", title: "ФСП" },
  { id: "github", title: "GitHub" },
  { id: "done", title: "Готово" },
];

function Soon({ text, onNext }: { text: string; onNext: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-muted">{text}</p>
      <p className="rounded-lg border border-hairline bg-tint-50 px-3 py-2 text-sm">
        Этот шаг подключим позже. Его можно пройти из профиля, когда он появится.
      </p>
      <Button variant="ghost" onClick={onNext}>
        Пропустить
      </Button>
    </div>
  );
}

/**
 * Онбординг кандидата (макет M1): шаги на вертикальной схемной линии, любой шаг можно пропустить.
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

  return (
    <section className="mx-auto flex w-full max-w-lg flex-col gap-5 py-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold">Соберём ваш профиль</h1>
        <p className="text-sm text-muted">
          Шаг {index + 1} из {STEPS.length}. Каждый шаг можно пропустить и вернуться позже.
        </p>
      </header>

      <ol className="relative flex flex-col gap-4 border-l-2 border-tint-200 pl-5">
        {STEPS.map((s, i) => {
          const state = i < index ? "past" : i === index ? "current" : "future";
          return (
            <li key={s.id} aria-current={state === "current" ? "step" : undefined} className="relative flex flex-col gap-3">
              <span
                aria-hidden
                className={cn(
                  "absolute -left-[29px] top-1 size-3.5 rounded-full border-2",
                  state === "past" && "border-brand bg-brand",
                  state === "current" && "border-signal bg-signal",
                  state === "future" && "border-dashed border-brand-mid bg-page",
                )}
              />
              <h2 className={cn("font-semibold", state === "future" && "text-muted")}>
                {i + 1} · {s.title}
                {state === "past" && (
                  <span className="ml-2 text-xs font-normal text-muted">
                    {outcome[s.id] === "skipped" ? "пропущено" : s.id === "resume" && skills !== null ? `навыков: ${skills}` : "готово"}
                  </span>
                )}
              </h2>
              {state === "current" && s.id === "resume" && (
                <ResumeStep
                  onDone={(n) => {
                    setSkills(n);
                    finish("resume", "done");
                  }}
                  onSkip={() => finish("resume", "skipped")}
                />
              )}
              {state === "current" && s.id === "fsp" && (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted">
                    Результаты соревнований ФСП — самое сильное подтверждение: они поднимут навыки и грейд.
                  </p>
                  <FspLinkPanel next="/onboarding" onLinked={() => finish("fsp", "done")} />
                  <Button variant="ghost" onClick={() => finish("fsp", "skipped")}>
                    {params.get("fsp") === "linked" ? "Дальше" : "Пропустить"}
                  </Button>
                </div>
              )}
              {state === "current" && s.id === "github" && (
                <Soon
                  text="Читаем только публичные репозитории, токен не нужен. Код не запускается."
                  onNext={() => finish("github", "skipped")}
                />
              )}
              {state === "current" && s.id === "done" && (
                <div className="flex flex-col gap-3">
                  <p className="text-sm text-muted">
                    {outcome.resume === "done"
                      ? "Резюме добавлено. Остальные подтверждения можно добавить позже, они поднимут доверие к навыкам."
                      : "Профиль создан без резюме. Его можно загрузить позже."}
                  </p>
                  <Link
                    to="/me"
                    className="inline-flex h-12 items-center justify-center rounded-lg bg-brand px-5 font-semibold text-on-brand hover:bg-brand-deep"
                  >
                    Смотреть мой профиль
                  </Link>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
