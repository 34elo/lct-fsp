import { InfoTip } from "@fsp/ui";
import type { ReactNode } from "react";

import { GLOSSARY, type GlossaryKey } from "./glossary";

/** Значок ⓘ с пояснением термина из словаря. Ставится рядом с названием термина. */
export function Gi({ k, className }: { k: GlossaryKey; className?: string }) {
  const g = GLOSSARY[k];
  return (
    <InfoTip title={g.title} label={`Что такое «${g.title}»`} className={className} data-testid={`gi-${k}`}>
      {g.text}
    </InfoTip>
  );
}

/** Термин с ⓘ: `<Gloss k="trust">Доверие</Gloss>`. */
export function Gloss({ k, children, className }: { k: GlossaryKey; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 ${className ?? ""}`}>
      {children}
      <Gi k={k} />
    </span>
  );
}
