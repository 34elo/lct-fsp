import { cn, Panel, SkillTag, StatusTag } from "@fsp/ui";
import type { CSSProperties, ReactNode } from "react";

import { Reveal } from "./motion";
import { hoverLift, SecHead, sectionY, Wrap } from "./parts";
import { T } from "./text";

const mono13 = "font-mono text-13 text-muted";
const code = "m-0 overflow-hidden rounded-lg bg-code-bg px-3 py-2.5 font-mono text-13 leading-[1.6] whitespace-pre text-code-fg";

function Card({ title, text, delay, children }: { title: string; text: string; delay: number; children: ReactNode }) {
  return (
    <Reveal delay={delay} className="min-w-0">
      <Panel className={cn("flex h-full flex-col gap-3 p-5 min-[861px]:p-7", hoverLift)}>
        <h3 className="m-0 font-mono text-[19px] leading-[1.3] font-semibold">{title}</h3>
        <p className="m-0 text-[15px] text-muted">{text}</p>
        <div className="mt-2.5 flex min-h-[132px] flex-col justify-center gap-2.5 rounded-[10px] border border-hairline bg-tint-50 p-4 dark:bg-page">{children}</div>
      </Panel>
    </Reveal>
  );
}

const K = ({ children }: { children: ReactNode }) => <span className="text-brand-mid">{children}</span>;

/** Блок «Почему этому можно верить»: четыре карточки с живой иллюстрацией. Иллюстрации не кликабельны. */
export function Trust() {
  return (
    <section id="trust" tabIndex={-1} className={cn("outline-none", sectionY)}>
      <Wrap>
        <Reveal className="mb-7 flex flex-col min-[861px]:mb-10">
          <SecHead label={T.trustLabel} title={T.trustTitle} />
        </Reveal>
        <div className="grid grid-cols-1 gap-5 min-[861px]:grid-cols-2">
          <Card title={T.variantTitle} text={T.variantText} delay={0}>
            <div className="grid grid-cols-1 gap-2.5 min-[861px]:grid-cols-2">
              <div className="min-w-0">
                <span className={cn(mono13, "mb-1.5 block")}>{T.variantMine}</span>
                <pre className={code}>
                  <K>print</K>(<K>len</K>({"{1, 2, 2, 3}"}))
                </pre>
              </div>
              <div className="min-w-0">
                <span className={cn(mono13, "mb-1.5 block")}>{T.variantOther}</span>
                <pre className={code}>
                  <K>print</K>(<K>len</K>({"{4, 4, 5, 6, 6}"}))
                </pre>
              </div>
            </div>
          </Card>

          <Card title={T.stopTitle} text={T.stopText} delay={80}>
            <div className="flex items-center justify-between gap-2.5">
              <span className={mono13}>{T.stopTask}</span>
              <span className={mono13}>{T.stopConfidence}</span>
            </div>
            <div className="grid grid-cols-[repeat(30,1fr)] gap-[3px]" aria-hidden="true">
              {Array.from({ length: 30 }, (_, i) => (
                <i
                  key={i}
                  className={cn("lp-tick h-[18px] rounded-[2px]", i < 5 && "lp-tick-f")}
                  style={i < 5 ? ({ "--i": i } as CSSProperties) : undefined}
                />
              ))}
            </div>
            <div className="lp-bar h-2 overflow-hidden rounded bg-tint-100" style={{ "--w": "92%" } as CSSProperties}>
              <b className="block h-full rounded bg-brand" />
            </div>
          </Card>

          <Card title={T.hintTitle} text={T.hintText} delay={0}>
            <div className="flex flex-wrap items-center gap-2.5">
              <SkillTag name={T.hintSkill} />
              <b className="text-14 font-semibold">{T.hintMistake}</b>
            </div>
            <pre className={code}>
              LEFT JOIN orders o ON o.user_id = u.id{"\n"}
              <span className="-mx-3 block bg-code-mark px-3">WHERE o.status = &apos;paid&apos;</span>
            </pre>
            <div className="flex flex-wrap items-center gap-2.5">
              <StatusTag>{T.hintLearn}</StatusTag>
              <span className={mono13}>{T.hintTopic}</span>
            </div>
          </Card>

          <Card title={T.forkTitle} text={T.forkText} delay={80}>
            <div className="flex items-center justify-between gap-2.5">
              <span className="font-mono text-[30px] leading-[1.05] font-bold tracking-[-0.02em]">{T.forkRange}</span>
              <span className={mono13}>{T.forkBasis}</span>
            </div>
            <div className="relative h-9" aria-hidden="true">
              <i className="absolute inset-x-0 top-[15px] h-1.5 rounded-[3px] bg-tint-100" />
              <i className="absolute top-[11px] left-[22%] h-3.5 w-[56%] rounded-[7px] bg-brand" />
            </div>
            <div className={mono13}>{T.forkNote}</div>
          </Card>
        </div>
      </Wrap>
    </section>
  );
}
