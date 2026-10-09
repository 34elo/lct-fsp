import { Logo, toast } from "@fsp/ui";
import { Link } from "react-router-dom";

import { Net } from "./Hero";
import { JuryEntry } from "./JuryEntry";
import { juryEnabled } from "./jury";
import { onAnchorClick, Reveal } from "./motion";
import { CtaPair, Wrap } from "./parts";
import { T } from "./text";

/** Финальный призыв: те же две кнопки (T1, T2) на фоне бренда. */
export function Final() {
  return (
    <section className="pt-14 pb-14 min-[861px]:pt-24 min-[861px]:pb-[72px]">
      <Reveal className="relative mx-4 overflow-hidden rounded-2xl bg-brand px-5 py-12 text-center text-white min-[861px]:mx-6 min-[861px]:px-6 min-[861px]:py-20">
        <Net white className="opacity-50" />
        <h2 className="relative m-0 font-mono text-[28px] leading-[1.1] font-bold tracking-[-0.02em] min-[861px]:text-[44px]">{T.finalTitle}</h2>
        <CtaPair onBrand className="relative mt-8" />
        <p className="relative mt-5 mb-0 text-[#e6e4ff]">{T.finalNote}</p>
      </Reveal>
    </section>
  );
}

const footLink = "transition-colors duration-150 hover:text-ink";

/** Подвал: Условия, Политика ПДн, Контакты (T5). «Демо для жюри» (T6) и вход жюри — только при `VITE_JURY_MODE`. */
export function Footer() {
  const jury = juryEnabled();
  return (
    <footer className="pt-12 pb-10">
      <Wrap className="flex flex-col items-start justify-between gap-6 min-[861px]:flex-row min-[861px]:items-center min-[861px]:flex-wrap">
        {jury && (
          <div id="jury" tabIndex={-1} className="w-full scroll-mt-20 outline-none">
            <JuryEntry />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-7">
          <Link to="/" aria-label="На главную" className="inline-flex rounded-md">
            <Logo />
          </Link>
          <nav aria-label={T.footerAria} className="flex gap-6 text-14 text-muted">
            <Link to="/terms" className={footLink}>
              {T.terms}
            </Link>
            <Link to="/privacy" className={footLink}>
              {T.privacy}
            </Link>
            <button
              type="button"
              className={footLink}
              onClick={() =>
                toast(T.contactToast, { action: { label: T.contactOpen, onClick: () => window.open(T.contactUrl, "_blank", "noopener,noreferrer") } })
              }
            >
              {T.contacts}
            </button>
          </nav>
        </div>
        {jury && (
          <a href="#jury" onClick={onAnchorClick("jury")} className="text-12 text-muted underline underline-offset-[3px] opacity-80 hover:text-ink">
            {T.demo}
          </a>
        )}
        <div className="mt-1 w-full text-13 text-muted">{T.copyright}</div>
      </Wrap>
    </footer>
  );
}
