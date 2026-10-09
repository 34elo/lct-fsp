import { cn, Panel } from "@fsp/ui";
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import { Reveal, useLayoutMeasure } from "./motion";
import { hoverLift, SecHead, sectionY, Wrap } from "./parts";
import { T } from "./text";

const ICONS: Record<string, ReactNode> = {
  target: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
    </>
  ),
  test: (
    <>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4V3h6v1" />
      <path d="M9 13l2 2 4-4" />
    </>
  ),
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M3 7l9 6 9-6" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="M20 20l-4.2-4.2" />
    </>
  ),
  grid: (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </>
  ),
  send: <path d="M21 3L3 11l7 3 3 7 8-18z" />,
};

function Steps({ steps }: { steps: readonly { title: string; text: string; icon: string }[] }) {
  return (
    <div className="relative grid grid-cols-1 gap-5 min-[861px]:grid-cols-3">
      <i className="lp-line absolute top-[47px] right-[17%] left-[17%] z-0 hidden h-0.5 origin-left bg-brand opacity-55 min-[861px]:block" aria-hidden="true" />
      {steps.map((s, i) => (
        <Panel key={s.title} className={cn("lp-step relative z-[1] flex flex-col gap-3.5 p-6", hoverLift)}>
          <span className="absolute top-[18px] right-5 font-mono text-[15px] font-bold text-muted">{i + 1}</span>
          <div className="grid size-12 place-items-center rounded-xl border border-tint-200 bg-tint-50 text-brand-fg">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {ICONS[s.icon]}
            </svg>
          </div>
          <h3 className="m-0 font-mono text-[19px] leading-[1.3] font-semibold">{s.title}</h3>
          <p className="m-0 text-[15px] text-muted">{s.text}</p>
        </Panel>
      ))}
    </div>
  );
}

const TABS = [
  { id: "candidate", label: T.tabCandidate, steps: T.candidateSteps },
  { id: "company", label: T.tabCompany, steps: T.companySteps },
] as const;

/** Блок «Как это работает»: вкладки «Кандидату / Компании» (A4) и по три шага (A5). Стрелки ← → переключают вкладки. */
export function How() {
  const [active, setActive] = useState(0);
  const [pill, setPill] = useState<{ x: number; w: number } | null>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);

  useLayoutMeasure(() => {
    const el = tabs.current[active];
    if (el && el.offsetWidth > 0) setPill({ x: el.offsetLeft, w: el.offsetWidth });
  }, [active]);

  function onKey(e: KeyboardEvent, i: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    const next = e.key === "Home" ? 0 : e.key === "End" ? TABS.length - 1 : (i + step + TABS.length) % TABS.length;
    if (!step && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    setActive(next);
    tabs.current[next]?.focus();
  }

  return (
    <section id="how" tabIndex={-1} className={cn("bg-tint-50 outline-none dark:bg-card", sectionY)}>
      <Wrap>
        <Reveal className="mb-7 flex flex-col min-[861px]:mb-10">
          <SecHead label={T.howLabel} title={T.howTitle} />
        </Reveal>
        <Reveal delay={60}>
          <div role="tablist" aria-label={T.tabsAria} className="relative mb-8 flex rounded-xl border border-hairline bg-card p-1 min-[861px]:inline-flex">
            <i
              aria-hidden="true"
              data-ready={pill !== null}
              className="lp-pillbg absolute top-1 bottom-1 left-0 z-0 rounded-lg bg-brand"
              style={{ width: pill?.w ?? 0, transform: `translateX(${pill?.x ?? 0}px)` }}
            />
            {TABS.map((t, i) => (
              <button
                key={t.id}
                ref={(el) => void (tabs.current[i] = el)}
                type="button"
                role="tab"
                id={`how-${t.id}-tab`}
                aria-controls={`how-${t.id}`}
                aria-selected={active === i}
                tabIndex={active === i ? 0 : -1}
                onClick={() => setActive(i)}
                onKeyDown={(e) => onKey(e, i)}
                className={cn(
                  "relative z-[1] flex-1 rounded-lg px-2 py-2.5 font-mono text-[15px] font-semibold transition-colors duration-200 min-[861px]:flex-none min-[861px]:px-[22px]",
                  active === i ? "text-white" : "text-muted",
                  active === i && !pill && "bg-brand",
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          {TABS.map((t, i) => (
            <div key={t.id} id={`how-${t.id}`} role="tabpanel" aria-labelledby={`how-${t.id}-tab`} hidden={active !== i} className="lp-panel">
              <Steps steps={t.steps} />
            </div>
          ))}
        </Reveal>
      </Wrap>
    </section>
  );
}
