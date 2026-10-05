import { useEffect, useState, type ReactNode } from "react";

import { Button, ConstellationAvatar, Logo, MatchRing, SkillChip, TrustDots, type TrustKind } from "../src";
import { DEMO_CANDIDATES, DEMO_SKILLS, RADII, TOKEN_GROUPS } from "./data";

type Page = "tokens" | "base" | "brand";
const PAGES: { id: Page; title: string }[] = [
  { id: "tokens", title: "Токены" },
  { id: "base", title: "Базовые" },
  { id: "brand", title: "Фирменные" },
];
const KINDS: TrustKind[] = ["verified", "inferred", "adjacent", "claimed", "provisional"];

function readHash(): Page {
  const h = location.hash.replace("#", "");
  return PAGES.some((p) => p.id === h) ? (h as Page) : "tokens";
}

/** Тема: `?theme=dark` (для `pnpm shot`) или ключ `fsp-theme`, как в приложении. */
function readTheme(): boolean {
  const q = new URLSearchParams(location.search).get("theme");
  if (q) return q === "dark";
  try {
    return localStorage.getItem("fsp-theme") === "dark";
  } catch {
    return false;
  }
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-hairline bg-card p-5">
      <h2 className="mb-4 text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Tokens() {
  return (
    <div className="grid gap-5">
      {TOKEN_GROUPS.map((g) => (
        <Section key={g.title} title={g.title}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {g.tokens.map((t) => (
              <div key={t} className="flex flex-col gap-1.5">
                <div className="h-14 rounded-md border border-hairline" style={{ background: `var(--${t})` }} />
                <code className="font-mono text-xs text-muted">--{t}</code>
              </div>
            ))}
          </div>
        </Section>
      ))}
      <Section title="Шрифты">
        <p className="font-sans text-2xl">Onest — ФСП Карьера: доказанные навыки</p>
        <p className="font-mono text-base">JetBrains Mono — Кандидат #4821 · 275 000 ₽</p>
      </Section>
      <Section title="Радиусы">
        <div className="flex flex-wrap gap-4">
          {RADII.map((r) => (
            <div key={r} className="flex flex-col items-center gap-1.5">
              <div className="size-16 border border-brand bg-tint-50" style={{ borderRadius: `var(--radius-${r})` }} />
              <code className="font-mono text-xs text-muted">{r}</code>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

function Base() {
  return (
    <div className="grid gap-5">
      {(["primary", "outline", "ghost"] as const).map((variant) => (
        <Section key={variant} title={`Button · ${variant}`}>
          <div className="flex flex-wrap items-center gap-3">
            {(["sm", "md", "lg"] as const).map((size) => (
              <Button key={size} variant={variant} size={size}>
                Пригласить · {size}
              </Button>
            ))}
            <Button variant={variant} disabled>
              Недоступно
            </Button>
          </div>
        </Section>
      ))}
    </div>
  );
}

function Brand() {
  return (
    <div className="grid gap-5">
      <Section title="Logo">
        <div className="flex flex-wrap items-center gap-6">
          <Logo />
          <Logo mark />
        </div>
      </Section>
      <Section title="TrustDots">
        <div className="grid gap-2">
          {KINDS.map((k) => (
            <div key={k} className="flex flex-wrap items-center gap-3">
              <code className="w-28 font-mono text-xs text-muted">{k}</code>
              {([1, 2, 3, 4] as const).map((l) => (
                <TrustDots key={l} level={l} kind={k} />
              ))}
            </div>
          ))}
        </div>
      </Section>
      <Section title="SkillChip">
        <div className="flex flex-wrap gap-2">
          {DEMO_SKILLS.map((s) => (
            <SkillChip key={s.name} name={s.name} level={s.level} variant={s.variant} />
          ))}
        </div>
      </Section>
      <Section title="ConstellationAvatar и MatchRing">
        <div className="grid gap-3">
          {DEMO_CANDIDATES.map((c) => (
            <div key={c.pseudo} className="flex items-center gap-4 rounded-lg border border-hairline p-3">
              <ConstellationAvatar seed={c.pseudo} />
              <div className="min-w-0 flex-1">
                <b className="font-mono">{c.pseudo}</b>
                <p className="text-sm text-muted">
                  {c.title} · {c.note}
                </p>
              </div>
              <MatchRing value={c.match} />
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

export function Playground() {
  const [page, setPage] = useState<Page>(readHash);
  const [dark, setDark] = useState(readTheme);

  useEffect(() => {
    const on = () => setPage(readHash());
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-5 px-4 py-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-bold">@fsp/ui</h1>
        <nav className="flex gap-1" aria-label="Разделы">
          {PAGES.map((p) => (
            <a
              key={p.id}
              href={`#${p.id}`}
              aria-current={page === p.id ? "page" : undefined}
              className="rounded-md px-3 py-1.5 text-sm font-medium hover:bg-tint-50 aria-[current=page]:bg-tint-100"
            >
              {p.title}
            </a>
          ))}
        </nav>
        <Button variant="outline" size="sm" onClick={() => setDark((d) => !d)} aria-pressed={dark}>
          {dark ? "Светлая тема" : "Тёмная тема"}
        </Button>
      </header>
      {page === "tokens" && <Tokens />}
      {page === "base" && <Base />}
      {page === "brand" && <Brand />}
    </div>
  );
}
