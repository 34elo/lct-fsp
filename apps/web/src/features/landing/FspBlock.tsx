import { cn, StatusTag, ThemeScope } from "@fsp/ui";

import { Reveal } from "./motion";
import { hoverLift, SecLabel, SecTitle, sectionY, Wrap } from "./parts";
import { T } from "./text";

/** Блок ФСП: тёмный в обеих темах. Карточка достижения и шкала «место в категории» (A7: маркер «с ФСП» едет к топ-30 %). */
export function FspBlock() {
  return (
    <ThemeScope dark>
      <section id="fsp" tabIndex={-1} className={cn("bg-[var(--band)] outline-none", sectionY)}>
        <Wrap className="grid items-center gap-7 min-[861px]:grid-cols-2 min-[861px]:gap-14">
          <Reveal>
            <SecLabel className="text-brand-mid">{T.fspLabel}</SecLabel>
            <SecTitle className="mt-2 text-white">{T.fspTitle}</SecTitle>
            <p className="mt-2.5 mb-0 text-[15px] text-muted min-[861px]:text-[17px]">{T.fspLead}</p>
          </Reveal>
          <Reveal delay={100}>
            <div className={cn("flex flex-col gap-[18px] rounded-xl border border-hairline bg-[var(--ach)] p-6 text-ink", hoverLift)}>
              <div className="flex items-start gap-3.5">
                <span className="grid size-10 flex-none place-items-center rounded-[10px] bg-brand font-mono text-14 font-bold text-white">ФСП</span>
                <div>
                  <StatusTag className="mb-2">{T.fspBadge}</StatusTag>
                  <div className="mt-1.5 text-[17px] leading-[1.35] font-semibold">{T.fspAchievement}</div>
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between gap-2.5 font-mono text-13 text-muted">
                  <span>{T.fspCategory}</span>
                  <span>{T.fspPlace}</span>
                </div>
                <div className="relative mt-1.5 h-14" role="img" aria-label={`${T.fspWithout}; ${T.fspWith}`}>
                  <i className="absolute inset-x-0 top-[22px] h-1.5 rounded-[3px] bg-hairline" />
                  <i className="lp-rail-fill absolute top-[22px] left-0 h-1.5 rounded-[3px] bg-brand" />
                  <div className="absolute top-3.5 left-[38%] flex -translate-x-1/2 flex-col items-center gap-1.5 font-mono text-11 font-semibold whitespace-nowrap text-brand-mid">
                    <i className="mt-0.5 size-[18px] rounded-full border-2 border-brand-mid bg-[var(--ach)]" />
                    <span className="mt-0.5">{T.fspWithout}</span>
                  </div>
                  <div className="lp-mk-me absolute top-3.5 flex -translate-x-1/2 flex-col items-center gap-1.5 font-mono text-11 font-semibold whitespace-nowrap text-white">
                    <i className="size-[22px] rounded-full border-4 border-[var(--ach)] bg-brand shadow-[0_0_0_1px_var(--brand)]" />
                    <span className="mt-0.5">{T.fspWith}</span>
                  </div>
                </div>
              </div>
            </div>
          </Reveal>
        </Wrap>
      </section>
    </ThemeScope>
  );
}
