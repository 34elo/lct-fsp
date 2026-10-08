import { localSkillSource, type SkillSource, type SkillSuggestion } from "@fsp/ui";
import { useMemo } from "react";

import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";

/** Навык справочника, как его отдаёт `/taxonomy` (схема ответа не описана в OpenAPI). */
export interface TaxonomySkill {
  slug: string;
  name: string;
}

/**
 * Навыки справочника и источник подсказок для `SkillInput`.
 * Пока нет `/taxonomy/skills/suggest` (E39-3), подсказки ищутся по справочнику на клиенте;
 * после E39-3 здесь меняется только `suggest`, экраны не трогаем.
 */
export function useSkillSource(): { skills: TaxonomySkill[]; suggest: SkillSource; nameOf: (slug: string) => string; isPending: boolean } {
  const q = useGetTaxonomyTaxonomyGet();
  const skills = useMemo(() => (q.data?.data as { skills?: TaxonomySkill[] } | undefined)?.skills ?? [], [q.data]);
  return useMemo(() => {
    const names = new Map(skills.map((s) => [s.slug, s.name]));
    const list: SkillSuggestion[] = skills.map((s) => ({ slug: s.slug, name: s.name }));
    return { skills, suggest: localSkillSource(list), nameOf: (slug: string) => names.get(slug) ?? slug, isPending: q.isPending };
  }, [skills, q.isPending]);
}
