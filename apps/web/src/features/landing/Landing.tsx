import { buttonVariants, CircuitLine, cn, Logo, MatchRing, SalaryRange, SectionLabel, SkillChip, ThemeScope } from "@fsp/ui";
import { Link } from "react-router-dom";

import { ThemeToggle } from "@/app/layouts/Shell";
import { JuryEntry } from "./JuryEntry";
import { T } from "./text";

const cta = "h-12 px-6 text-16";
const pad = "px-4 md:px-12 lg:px-20";
const h2 = "font-mono text-24 font-semibold md:text-32";

function Hero() {
  return (
    <ThemeScope dark>
      <header className={pad}>
        <div className="flex h-[72px] items-center justify-between gap-3">
          <Link to="/" aria-label="На главную">
            <Logo />
          </Link>
          <nav aria-label={T.navAria} className="flex items-center gap-3 text-14">
            <ThemeToggle />
            <Link to="/login" className={buttonVariants({ variant: "outline" })}>
              {T.login}
            </Link>
          </nav>
        </div>
        <div className="grid items-center gap-10 pb-16 pt-8 lg:grid-cols-[1.1fr_1fr] lg:gap-16 lg:pb-24 lg:pt-16">
          <div className="flex flex-col gap-5">
            <SectionLabel className="text-brand-fg">{T.eyebrow}</SectionLabel>
            <h1 className="font-mono text-[32px] font-semibold leading-[1.1] tracking-tight md:text-[56px]">{T.heroTitle}</h1>
            <p className="max-w-[560px] text-16 text-muted md:text-20">{T.heroLead}</p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Link to="/register" className={cn(buttonVariants({ variant: "default" }), cta)}>
                {T.ctaCandidate}
              </Link>
              <Link to="/register" className={cn(buttonVariants({ variant: "outline" }), cta)}>
                {T.ctaEmployer}
              </Link>
            </div>
            <JuryEntry />
          </div>
          <HeroCard />
        </div>
      </header>
    </ThemeScope>
  );
}

/** Статичная карточка-пример: вымышленная компания, не данные API. */
function HeroCard() {
  return (
    <div className="relative lg:pl-10" aria-hidden="true">
      <div className="flex flex-col gap-3 rounded-2xl bg-card p-5 shadow-card">
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-lg bg-tint-100 font-mono font-bold">СК</span>
          <div>
            <b>{T.offerCompany}</b>
            <p className="text-12 text-muted">{T.offerMeta}</p>
          </div>
        </div>
        <SalaryRange label={T.offerLabel} from={200000} to={250000} size="offer" />
        <p className="font-semibold">{T.offerRole}</p>
        <div className="flex flex-wrap gap-2">
          <SkillChip name={T.offerChip} />
          <SkillChip name="FastAPI" level={4} />
        </div>
      </div>
      <div className="mt-4 flex w-fit items-center gap-3 rounded-xl border border-hairline bg-card p-3 lg:absolute lg:-bottom-8 lg:left-0 lg:mt-0">
        <MatchRing value={92} size={48} />
        <div className="text-13">
          <b>{T.matchTitle}</b>
          <p className="text-brand-fg">{T.matchWho}</p>
        </div>
      </div>
    </div>
  );
}

function How() {
  return (
    <section className={cn("flex flex-col gap-8 py-14 md:py-20", pad)}>
      <h2 className={h2}>{T.how}</h2>
      <CircuitLine
        className="hidden md:flex"
        orientation="horizontal"
        steps={T.steps.map((s, i) => ({ id: String(i + 1), label: s.title, state: i === 0 ? "current" : "future" }))}
      />
      <div className="grid gap-4 md:grid-cols-3">
        {T.steps.map((s, i) => (
          <div key={s.title} className="flex flex-col gap-2 rounded-xl border border-hairline bg-card p-5">
            <span className="font-mono text-[28px] font-bold text-brand-fg">{i + 1}</span>
            <h3 className="font-mono text-16 font-semibold">{s.title}</h3>
            <p className="text-14 text-muted">{s.text}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function Graph() {
  return (
    <section className={pad}>
      <ThemeScope dark className="grid items-center gap-8 rounded-2xl p-6 md:p-10 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <SectionLabel className="text-brand-fg">{T.graphLabel}</SectionLabel>
          <h2 className={h2}>{T.graphTitle}</h2>
          <p className="text-muted">{T.graphText}</p>
        </div>
        <div className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-5" aria-hidden="true">
          <div className="flex flex-wrap gap-2">
            <SkillChip name="FastAPI" level={4} />
            <SkillChip name="PostgreSQL" level={3} />
            <SkillChip name="Python" level={4} />
            <SkillChip name="Docker" level={1} variant="inferred" />
          </div>
          <p className="text-12 text-muted">{T.graphSource}</p>
        </div>
      </ThemeScope>
    </section>
  );
}

function MapBlock() {
  return (
    <section className={cn("grid items-center gap-6 py-14 md:py-20 lg:grid-cols-2", pad)}>
      <div className="flex flex-col gap-3">
        <SectionLabel>{T.mapLabel}</SectionLabel>
        <h2 className={h2}>{T.mapTitle}</h2>
      </div>
      <img src="/brand/map-russia.png" alt={T.mapAlt} loading="lazy" className="w-full rounded-xl border border-hairline bg-card" />
    </section>
  );
}

function Audience() {
  const cards = [
    { title: T.candidates, items: T.candidatesList, cta: T.candidatesCta},
    { title: T.employers, items: T.employersList, cta: T.employersCta },
  ];
  return (
    <section className={cn("grid gap-4 pb-14 md:grid-cols-2 md:pb-20", pad)}>
      {cards.map((c) => (
        <div key={c.title} className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-5">
          <h3 className="font-mono text-20 font-semibold">{c.title}</h3>
          <ul className="flex flex-1 flex-col gap-2 text-14 text-muted">
            {c.items.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
          <Link to="/register" className={cn(buttonVariants({ variant: "default" }), "w-full sm:w-fit")}>
            {c.cta}
          </Link>
        </div>
      ))}
    </section>
  );
}

function Fsp() {
  return (
    <section className={cn("flex flex-col gap-6 pb-14 md:pb-20", pad)}>
      <SectionLabel>{T.fsp}</SectionLabel>
      <h2 className={h2}>{T.fspTitle}</h2>
      <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {T.fspCycle.map((s, i) => (
          <li key={s} className="flex items-center gap-3 rounded-xl border border-hairline bg-card p-4">
            <span className="font-mono text-20 font-bold text-brand-fg">{i + 1}</span>
            <span className="font-semibold">{s}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Footer() {
  return (
    <ThemeScope dark>
      <footer className={cn("flex flex-col gap-3 py-8 text-14 text-muted md:flex-row md:justify-between", pad)}>
        <span>{T.copyright}</span>
        <span className="flex gap-5">
          <Link to="/terms">{T.terms}</Link>
          <Link to="/privacy">{T.privacy}</Link>
          <a href="mailto:career@fsp.example">{T.contacts}</a>
        </span>
      </footer>
    </ThemeScope>
  );
}

/** Лендинг L1/L2. Счётчиков нет: `GET /public/stats` в сгенерированном клиенте отсутствует, блок скрыт (E19-14). */
export default function Landing() {
  return (
    <div className="bg-page text-ink">
      <Hero />
      <How />
      <Graph />
      <MapBlock />
      <Audience />
      <Fsp />
      <Footer />
    </div>
  );
}
