import {
  buttonVariants,
  Chips,
  cn,
  CompanyMark,
  GradeTag,
  H1,
  H2,
  Lbl,
  Logo,
  MatchRingV2,
  Num,
  Panel,
  SkillTag,
  ThemeScope,
} from "@fsp/ui";
import { Link } from "react-router-dom";

import { ThemeToggle } from "@/app/layouts/Shell";
import { JuryEntry } from "./JuryEntry";
import { juryEnabled } from "./jury";
import { T } from "./text";

const pad = "px-4 md:px-6 lg:px-[max(24px,calc((100%-1280px)/2))]";
const cta = "h-12 px-6 text-16";
const h2 = "m-0 font-mono text-[22px] font-semibold leading-[1.1] md:text-[30px]";

function Header() {
  return (
    <ThemeScope dark>
      <header className={cn("flex h-14 items-center gap-6 border-b border-hairline md:h-[60px]", pad)}>
        <Link to="/" aria-label="На главную">
          <Logo />
        </Link>
        <nav aria-label={T.navAria} className="hidden gap-5 text-14 md:flex">
          <a href="#steps" className="text-muted hover:text-ink">
            {T.navCandidates}
          </a>
          <a href="#fair" className="text-muted hover:text-ink">
            {T.navEmployers}
          </a>
        </nav>
        <span className="ml-auto flex items-center gap-3">
          <ThemeToggle />
          <Link to="/login" className={cn(buttonVariants({ variant: "outline" }), "h-9")}>
            {T.login}
          </Link>
        </span>
      </header>
    </ThemeScope>
  );
}

/** Карточка-пример: вымышленная компания, не данные API. */
function HeroCard() {
  return (
    <div className="relative flex flex-col gap-3" aria-hidden="true">
      <ThemeScope light className="flex flex-col gap-2.5 rounded-xl p-[18px] shadow-[0_20px_50px_rgba(0,0,0,.35)]">
        <div className="flex items-center gap-3">
          <CompanyMark name={T.offerCompany} />
          <div className="flex flex-col gap-0.5">
            <b className="font-semibold">{T.offerCompany}</b>
            <Num className="text-12 text-muted">{T.offerMeta}</Num>
          </div>
        </div>
        <Lbl>{T.offerLabel}</Lbl>
        <Num className="text-[24px] leading-[1.1] md:text-[30px]">{T.offerSalary}</Num>
        <span className="font-medium">{T.offerRole}</span>
        <Chips>
          <SkillTag name={T.offerChip} />
          <SkillTag name="Python" level={3} />
        </Chips>
      </ThemeScope>
      <div className="-mt-[26px] mr-3 flex items-center gap-3 self-end rounded-xl border border-hairline bg-card px-3.5 py-2">
        <MatchRingV2 value={92} size={36} />
        <div className="flex flex-col">
          <b className="text-13 font-semibold">{T.matchTitle}</b>
          <Num className="text-12 text-brand-fg">{T.matchWho}</Num>
        </div>
      </div>
    </div>
  );
}

function Hero() {
  const jury = juryEnabled();
  return (
    <ThemeScope dark>
      <section className={cn("py-8 md:py-[72px]", pad)}>
        <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_.9fr]">
          <div className="flex flex-col gap-5">
            <Lbl className="text-brand-fg">{T.eyebrow}</Lbl>
            <H1 className="text-[32px] leading-[1.08] font-bold md:text-[54px]">{T.heroTitle}</H1>
            <div className="flex flex-col gap-2.5 sm:flex-row sm:flex-wrap">
              <Link
                to="/register"
                state={{ role: "candidate" }}
                className={cn(buttonVariants({ variant: "default" }), cta)}
              >
                {T.ctaCandidate}
              </Link>
              <Link
                to="/register"
                state={{ role: "employer" }}
                className={cn(buttonVariants({ variant: "outline" }), cta)}
              >
                {T.ctaEmployer}
              </Link>
              {jury && (
                <a href="#jury" className={cn(buttonVariants({ variant: "link" }), cta)}>
                  {T.ctaJury}
                </a>
              )}
            </div>
            <div className="flex flex-wrap gap-7">
              {T.facts.map((f) => (
                <div key={f.label} className="flex flex-col gap-0.5">
                  <Num className="text-[22px]">{f.value}</Num>
                  <Lbl>{f.label}</Lbl>
                </div>
              ))}
            </div>
          </div>
          <HeroCard />
        </div>
        {jury && (
          <div id="jury" className="mt-10 scroll-mt-4">
            <JuryEntry />
          </div>
        )}
      </section>
    </ThemeScope>
  );
}

function Steps() {
  return (
    <section id="steps" className={cn("scroll-mt-4 py-8 md:py-[72px]", pad)}>
      <h2 className={cn(h2, "mb-5")}>{T.steps}</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <Panel className="flex flex-col gap-3.5 p-5">
          <Num className="text-[28px] text-brand-fg">1</Num>
          <H2 className="text-18">{T.step1}</H2>
          <div className="flex flex-wrap items-center gap-2">
            <GradeTag claimed>{T.gradeClaimed}</GradeTag>
            <span className="text-muted" aria-hidden="true">
              →
            </span>
            <GradeTag>{T.gradeConfirmed}</GradeTag>
          </div>
          <Num className="text-12">{T.confirmedAt}</Num>
        </Panel>
        <Panel className="flex flex-col gap-3.5 p-5">
          <Num className="text-[28px] text-brand-fg">2</Num>
          <H2 className="text-18">{T.step2}</H2>
          <div className="flex flex-col gap-2">
            <b className="font-mono text-16 font-semibold">{T.category}</b>
            <div className="flex flex-wrap gap-3.5">
              {T.categoryFacts.map((f) => (
                <Num key={f}>{f}</Num>
              ))}
            </div>
          </div>
        </Panel>
        <Panel className="flex flex-col gap-3.5 p-5">
          <Num className="text-[28px] text-brand-fg">3</Num>
          <H2 className="text-18">{T.step3}</H2>
          <div className="flex flex-col gap-1.5">
            <Num className="text-[22px]">{T.forkShort}</Num>
            <span className="text-13 text-muted">{T.forkWho}</span>
          </div>
        </Panel>
      </div>
    </section>
  );
}

function Fair() {
  return (
    <ThemeScope dark>
      <section id="fair" className={cn("scroll-mt-4 py-10 md:py-16", pad)}>
        <Lbl className="text-brand-fg">{T.fairLabel}</Lbl>
        <h2 className={cn(h2, "mb-5 mt-2")}>{T.fairTitle}</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <Panel className="flex flex-col gap-3 p-5">
            <Lbl>{T.worldCandidate}</Lbl>
            <b className="font-mono text-16 font-semibold">{T.worldCandidateTitle}</b>
            <Chips>
              {T.taskTypes.map((t) => (
                <SkillTag key={t} name={t} />
              ))}
            </Chips>
          </Panel>
          <Panel className="flex flex-col gap-3 p-5">
            <Lbl>{T.worldEmployer}</Lbl>
            <b className="font-mono text-16 font-semibold">{T.worldEmployerTitle}</b>
            <svg viewBox="0 0 400 70" width="100%" role="img" aria-label={T.scaleAria} fontFamily="var(--font-mono)">
              <rect x="4" y="22" width="116" height="16" rx="3" fill="var(--hairline)" />
              <rect x="124" y="22" width="96" height="16" rx="3" fill="var(--tint-200)" />
              <rect x="224" y="22" width="96" height="16" rx="3" fill="var(--brand-mid)" />
              <rect x="324" y="22" width="72" height="16" rx="3" fill="var(--brand)" />
              <g fontSize="11" fontWeight="600" fill="var(--ink)" textAnchor="middle">
                <text x="122" y="56">30</text>
                <text x="222" y="56">55</text>
                <text x="322" y="56">80</text>
              </g>
            </svg>
          </Panel>
        </div>
      </section>
    </ThemeScope>
  );
}

function Fsp() {
  return (
    <section className={cn("py-10 md:py-16", pad)}>
      <h2 className={cn(h2, "mb-5")}>{T.fsp}</h2>
      <div className="grid gap-4 md:grid-cols-2">
        <Panel className="flex flex-col gap-3 p-5">
          <Lbl>{T.fspAchievement}</Lbl>
          <div className="flex items-start gap-3">
            <Num className="grid size-7 flex-none place-items-center rounded-full bg-tint-100 text-chip-fg">1</Num>
            <b className="font-semibold">{T.fspAchievementText}</b>
          </div>
        </Panel>
        <Panel className="flex flex-col gap-2.5 p-5">
          <Lbl>{T.fspShare}</Lbl>
          {T.fspShares.map((s) => (
            <div key={s.name} className="flex items-center gap-3 py-1">
              <b className="font-mono text-16 font-semibold">{s.name}</b>
              <Num className="ml-auto text-[22px]">{s.value}</Num>
            </div>
          ))}
        </Panel>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <ThemeScope dark>
      <footer className={cn("flex flex-col gap-3 py-7 text-13 md:flex-row md:justify-between", pad)}>
        <span className="text-muted">{T.copyright}</span>
        <nav aria-label={T.footerAria} className="flex flex-wrap gap-x-5 gap-y-2">
          <Link to="/terms">{T.docs}</Link>
          <Link to="/privacy">{T.privacy}</Link>
          <a href="#steps">{T.about}</a>
          <a href={`mailto:${T.contactEmail}`}>{T.contacts}</a>
        </nav>
      </footer>
    </ThemeScope>
  );
}

/**
 * Лендинг `/` по v2_landing__*. Цифры и компания в примерах вымышленные и статичные: `GET /public/stats`
 * в клиенте нет, поэтому состояний loading/error у экрана нет (нечего грузить).
 */
export default function Landing() {
  return (
    <div className="bg-page text-ink">
      <Header />
      <Hero />
      <Steps />
      <Fair />
      <Fsp />
      <Footer />
    </div>
  );
}
