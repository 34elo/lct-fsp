import { buttonVariants, cn, Logo, Moon, Sun } from "@fsp/ui";
import { Link } from "react-router-dom";

import { AppLink } from "@/shared/lib/appUrl";
import { useTheme } from "@/shared/lib/theme";
import { Wrap } from "./parts";
import { onAnchorClick } from "./motion";
import { T } from "./text";

/** Шапка: логотип, якоря (T4), переключатель темы (A10, общий ThemeProvider) и «Войти» (T3). */
export function Header() {
  const { mode, setMode } = useTheme();
  const dark = mode === "dark";
  const Icon = dark ? Sun : Moon;
  return (
    <header
      data-lp-header
      className="sticky top-0 z-20 border-b border-hairline bg-[color-mix(in_srgb,var(--page)_88%,transparent)] backdrop-blur-[10px] backdrop-saturate-[1.4]"
    >
      <Wrap className="flex h-14 items-center gap-3 min-[861px]:h-16 min-[861px]:gap-7">
        <Link to="/" aria-label="На главную" className="inline-flex rounded-md">
          <Logo />
        </Link>
        <nav aria-label={T.navAria} className="ml-3 hidden gap-1 min-[861px]:flex">
          {T.nav.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              onClick={onAnchorClick(n.id)}
              className="rounded-lg px-3 py-2 font-medium text-muted transition-colors duration-150 hover:bg-tint-50 hover:text-ink dark:hover:bg-tint-100"
            >
              {n.label}
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => setMode(dark ? "light" : "dark")}
            aria-label={dark ? T.themeToLight : T.themeToDark}
            className="grid size-10 place-items-center rounded-lg border border-hairline bg-card text-ink transition-colors duration-150 hover:border-brand"
          >
            <Icon className="size-5" aria-hidden />
          </button>
          <AppLink to="/login" className={cn(buttonVariants({ variant: "outline" }), "h-10 rounded-lg px-[18px] text-14 dark:hover:bg-tint-100")}>
            {T.login}
          </AppLink>
        </div>
      </Wrap>
    </header>
  );
}
