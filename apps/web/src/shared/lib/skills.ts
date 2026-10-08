import { localSkillSource, type ProfessionOption, type ProfessionSource, type SkillSource, type SkillSuggestion } from "@fsp/ui";
import { useMemo } from "react";

import { useGetTaxonomyTaxonomyGet, suggestProfessionsTaxonomyProfessionsSuggestGet, suggestSkillsTaxonomySkillsSuggestGet } from "@/api/endpoints/taxonomy/taxonomy";

/** Навык справочника, как его отдаёт `/taxonomy` (схема ответа не описана в OpenAPI). */
export interface TaxonomySkill {
  slug: string;
  name: string;
}

/** Подсказка нового (ещё не подтверждённого) навыка помечается в списке. */
const PROVISIONAL_HINT = "новый";

/**
 * Навыки справочника и источник подсказок для `SkillInput`: серверные `/taxonomy/skills/suggest`
 * (синонимы, опечатки, частота; `profession` поднимает навыки профессии). Если сервер не ответил,
 * подсказки ищутся по справочнику на клиенте.
 */
export function useSkillSource(profession?: string): { skills: TaxonomySkill[]; suggest: SkillSource; nameOf: (slug: string) => string; isPending: boolean } {
  const q = useGetTaxonomyTaxonomyGet();
  const skills = useMemo(() => (q.data?.data as { skills?: TaxonomySkill[] } | undefined)?.skills ?? [], [q.data]);
  return useMemo(() => {
    const names = new Map(skills.map((s) => [s.slug, s.name]));
    const local = localSkillSource(skills.map((s) => ({ slug: s.slug, name: s.name })));
    const suggest: SkillSource = async (query, signal): Promise<SkillSuggestion[]> => {
      try {
        const r = await suggestSkillsTaxonomySkillsSuggestGet({ q: query, limit: 20, ...(profession ? { profession } : {}) }, { signal });
        if (r.status !== 200) return local(query, signal);
        return r.data.map((s) => ({ slug: s.slug, name: s.name, hint: s.provisional ? PROVISIONAL_HINT : undefined }));
      } catch (e) {
        if (signal.aborted) throw e;
        return local(query, signal);
      }
    };
    return { skills, suggest, nameOf: (slug: string) => names.get(slug) ?? slug, isPending: q.isPending };
  }, [skills, profession, q.isPending]);
}

/** Серверные подсказки профессий для `ProfessionInput`: все профессии системы, включая добавленные админом. */
export const suggestProfessions: ProfessionSource = async (query, signal): Promise<ProfessionOption[]> => {
  const r = await suggestProfessionsTaxonomyProfessionsSuggestGet({ q: query, limit: 20 }, { signal });
  return r.status === 200 ? r.data.map((p) => ({ slug: p.slug, title: p.title })) : [];
};
