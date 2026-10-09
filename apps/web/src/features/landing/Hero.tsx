import { cn, CompanyMark, H1, MatchRingV2, SkillTag } from "@fsp/ui";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { CtaPair, Wrap } from "./parts";
import { prefersReducedMotion, Reveal } from "./motion";
import { T } from "./text";

const card = "rounded-xl border border-hairline bg-card text-ink shadow-[0_24px_56px_rgba(27,28,33,.14)] dark:shadow-[0_24px_56px_rgba(0,0,0,.45)]";

/** Сетка из линий и узлов за иллюстрацией (декор). */
export function Net({ className, white }: { className?: string; white?: boolean }) {
  return (
    <svg
      className={cn("pointer-events-none absolute inset-0 z-0 size-full", className)}
      viewBox="0 0 1440 640"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      fill="none"
      strokeWidth="1.5"
    >
      {white ? (
        <path
          d="M0 120H220L280 180H520M1440 520H1180L1120 460H900M1000 80H1200L1260 140H1440M0 520H260L320 460H480"
          stroke="#fff"
          opacity=".35"
        />
      ) : (
        <>
          <g style={{ stroke: "var(--tint-200)" }}>
            <path d="M700 80H900L960 140H1180L1240 80H1440" />
            <path d="M820 560H1000L1060 500H1300L1360 560H1440" />
            <path d="M1020 250H1120L1160 290H1440" />
            <path d="M640 330H760L800 370H900" />
          </g>
          <g style={{ fill: "var(--brand)" }} stroke="none">
            {[
              [900, 80],
              [1180, 140],
              [1000, 560],
              [1300, 500],
              [1120, 250],
              [760, 330],
            ].map(([x, y]) => (
              <circle key={`${x}-${y}`} cx={x} cy={y} r="4" />
            ))}
          </g>
          <g style={{ fill: "var(--tint-200)" }} stroke="none">
            {[
              [1240, 80],
              [1060, 500],
              [800, 370],
              [1160, 290],
            ].map(([x, y]) => (
              <circle key={`${x}-${y}`} cx={x} cy={y} r="3" />
            ))}
          </g>
        </>
      )}
    </svg>
  );
}

/** A1: «прилёт» карточек; A2: параллакс слоёв (шире 860 px, не больше 24 px). Карточки не кликабельны. */
function Stage() {
  const [go, setGo] = useState(false);
  const layers = useRef<(HTMLDivElement | null)[]>([]);

  useEffect(() => {
    const t = setTimeout(() => setGo(true), prefersReducedMotion() ? 0 : 150);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (prefersReducedMotion()) return;
    let tick = false;
    const onScroll = () => {
      if (tick) return;
      tick = true;
      requestAnimationFrame(() => {
        tick = false;
        const wide = window.innerWidth > 860;
        layers.current.forEach((el, i) => {
          if (!el) return;
          const k = [0.03, 0.06, 0.09][i] ?? 0;
          el.style.transform = wide ? `translate3d(0,${-Math.min(24, window.scrollY * k).toFixed(1)}px,0)` : "";
        });
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const layer = (i: number, children: ReactNode) => (
    <div ref={(el) => void (layers.current[i] = el)} className="absolute inset-0 will-change-transform">
      {children}
    </div>
  );
  const fd = (ms: number) => ({ "--fd": `${ms}ms` }) as CSSProperties;
  const flyCls = go ? "go" : "";

  return (
    <div className="relative h-[392px] min-[861px]:h-[430px]" aria-hidden="true" data-testid="hero-stage">
      {layer(
        0,
        <div
          className={cn(
            "lp-fly lp-tilt absolute top-[22px] -right-[4%] left-[10%] h-[150px] origin-top-left px-[18px] py-3.5 opacity-90 min-[861px]:-right-[2%] min-[861px]:left-[14%]",
            card,
            flyCls,
          )}
          style={fd(270)}
        >
          <div className="flex items-center gap-3">
            <span className="grid size-10 flex-none place-items-center rounded-lg bg-brand-deep font-mono text-14 font-bold text-white">КС</span>
            <div>
              <b className="font-semibold">{T.secondCompany}</b>
              <div className="font-mono text-13 text-muted">{T.secondSalary}</div>
            </div>
          </div>
        </div>,
      )}
      {layer(
        1,
        <div
          className={cn(
            "lp-fly absolute inset-x-0 top-14 flex flex-col gap-3 p-4 min-[861px]:top-[62px] min-[861px]:right-[6%] min-[861px]:left-[4%] min-[861px]:p-[22px]",
            card,
            flyCls,
          )}
          style={fd(0)}
        >
          <div className="flex items-center justify-between gap-2.5">
            <div className="flex items-center gap-3">
              <CompanyMark name={T.offerCompany} size={40} className="border-0 bg-ink text-14 font-bold text-page" />
              <div>
                <b className="font-semibold">{T.offerCompany}</b>
                <div className="font-mono text-13 text-muted">{T.offerMeta}</div>
              </div>
            </div>
            <span className="font-mono text-13 text-muted">{T.inviteWord}</span>
          </div>
          <div>
            <div className="font-mono text-[32px] leading-[1.05] font-bold tracking-[-0.02em] min-[861px]:text-[40px]">{T.offerSalary}</div>
            <div className="mt-1.5 font-mono text-13 text-muted">{T.offerBasis}</div>
          </div>
          <div className="flex">
            <span className="inline-flex items-center rounded-sm border border-brand bg-brand px-2.5 py-1.5 font-mono text-12 leading-none font-semibold whitespace-nowrap text-on-brand">
              {T.offerGrade}
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {T.offerSkills.map((s) => (
              <SkillTag key={s.name} name={s.name} level={s.level} />
            ))}
          </div>
          <div className="text-13 text-muted">{T.offerNote}</div>
        </div>,
      )}
      {layer(
        2,
        <>
          <div
            className={cn(
              "lp-pop absolute -top-1.5 -left-[2%] z-[3] flex items-center gap-2 rounded-full px-3 py-2 font-mono text-13 font-medium",
              card,
              flyCls,
            )}
            style={fd(650)}
          >
            <i className="lp-dot size-2 rounded-full bg-signal" />
            {T.inviteNew}
          </div>
          <div
            className={cn("lp-pop absolute -right-[2%] bottom-0 z-[3] flex items-center gap-2.5 px-3.5 py-2.5 min-[861px]:-right-[1%] min-[861px]:bottom-2", card, flyCls)}
            style={fd(800)}
          >
            <MatchRingV2 value={92} size={40} />
            <div>
              <b className="text-14 font-semibold">{T.matchTitle}</b>
              <div className="font-mono text-13 text-muted">{T.matchWho}</div>
            </div>
          </div>
        </>,
      )}
    </div>
  );
}

export function Hero() {
  return (
    <section
      className="relative overflow-hidden bg-page pt-9 pb-12 min-[861px]:pt-[88px] min-[861px]:pb-[104px]"
      style={{
        backgroundImage: "radial-gradient(900px 520px at 78% 30%, color-mix(in srgb, var(--brand) 13%, transparent), transparent 70%)",
      }}
    >
      <Net className="opacity-90" />
      <Wrap className="z-[1] grid items-center gap-9 min-[861px]:grid-cols-[1.05fr_.95fr] min-[861px]:gap-12">
        <div className="relative">
          <Reveal className="font-mono text-[13px] font-medium tracking-[.02em] text-brand-fg">{T.eyebrow}</Reveal>
          <Reveal delay={60} className="mt-[18px]">
            <H1 className="text-[34px] leading-[1.06] font-bold tracking-[-0.02em] min-[861px]:text-[60px]">
              {T.heroTitle}
              <em className="text-brand-fg not-italic">{T.heroTitleEm}</em>
            </H1>
          </Reveal>
          <Reveal as="p" delay={120} className="mt-[22px] max-w-[520px] text-[17px] leading-[1.45] text-muted min-[861px]:mt-[26px] min-[861px]:text-xl">
            {T.heroLead}
          </Reveal>
          <Reveal delay={180} className="mt-6 min-[861px]:mt-9">
            <CtaPair />
          </Reveal>
        </div>
        <Stage />
      </Wrap>
    </section>
  );
}
