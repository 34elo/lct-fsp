import { useMemo } from "react";

import { Combobox, Search as SearchIcon, X, cn, type ComboOption } from "@fsp/ui";

import { suggestProfessionsTaxonomyProfessionsSuggestGet, suggestSkillsTaxonomySkillsSuggestGet } from "@/api/endpoints/taxonomy/taxonomy";
import { FIND_TEXT as T } from "./text";

/* Значения в строке: `s:<slug>` — навык, `p:<slug>` — профессия, `t:<фраза>` — разобрать текст (в строке не остаётся). */
const SKILL = "s:";
const PROF = "p:";
const TEXT = "t:";

export interface TagQueryProps {
  skills: string[];
  profession: string | null;
  skillName: (slug: string) => string;
  professionName: (slug: string) => string;
  onSkills: (slugs: string[], labels: Record<string, string>) => void;
  onProfession: (slug: string | null, label?: string) => void;
  /** Фраза целиком: разобрать в условия (`/search/parse`). */
  onParse: (text: string) => void;
  parsing: boolean;
  className?: string;
}

/** Подсказки системы: профессии и навыки (E39-3) плюс «разобрать фразу». Многословная фраза — первым пунктом. */
async function load(q: string, signal: AbortSignal, profession: string | null, chosen: Set<string>): Promise<ComboOption[]> {
  const t = q.trim();
  if (!t) return [];
  const [skills, profs] = await Promise.all([
    suggestSkillsTaxonomySkillsSuggestGet({ q: t, limit: 8, ...(profession ? { profession } : {}) }, { signal }).catch(() => null),
    suggestProfessionsTaxonomyProfessionsSuggestGet({ q: t, limit: 4 }, { signal }).catch(() => null),
  ]);
  if (signal.aborted) return [];
  const p = profs?.status === 200 ? profs.data.map<ComboOption>((x) => ({ value: PROF + x.slug, label: x.title, hint: T.hintProfession })) : [];
  const s =
    skills?.status === 200
      ? skills.data.map<ComboOption>((x) => ({ value: SKILL + x.slug, label: x.name, hint: x.provisional ? T.hintNew : T.hintSkill }))
      : [];
  // Уже выбранное не предлагаем: Enter по нему снял бы чипс.
  const fresh = (o: ComboOption) => !chosen.has(o.value);
  const parse: ComboOption = { value: TEXT + t, label: T.parseOption(t), hint: "Enter" };
  const found = [...p, ...s].filter(fresh);
  return /\s/.test(t) ? [parse, ...found] : [...found, parse];
}

/**
 * Строка запроса с тегами: навыки и профессия вставляются чипсами из подсказок системы, фраза целиком
 * разбирается в условия. Клавиатура — как у `Combobox` (↑ ↓ Enter Esc, Backspace убирает последний чипс).
 */
export function TagQuery({ skills, profession, skillName, professionName, onSkills, onProfession, onParse, parsing, className }: TagQueryProps) {
  const value = useMemo(() => [...(profession ? [PROF + profession] : []), ...skills.map((s) => SKILL + s)], [skills, profession]);
  const selected = useMemo<ComboOption[]>(
    () => [...(profession ? [{ value: PROF + profession, label: professionName(profession) }] : []), ...skills.map((s) => ({ value: SKILL + s, label: skillName(s) }))],
    [skills, profession, skillName, professionName],
  );
  const loadOptions = useMemo(() => (q: string, signal: AbortSignal) => load(q, signal, profession, new Set(value)), [profession, value]);

  const onChange = (next: string[], opts: ComboOption[]) => {
    const text = next.find((v) => v.startsWith(TEXT));
    if (text) return onParse(text.slice(TEXT.length));
    const profs = next.filter((v) => v.startsWith(PROF));
    // Профессия одна: новая заменяет прежнюю.
    const nextProf = profs.find((v) => v !== PROF + profession) ?? profs[0] ?? null;
    if ((nextProf?.slice(PROF.length) ?? null) !== profession) {
      const o = opts.find((x) => x.value === nextProf);
      onProfession(nextProf ? nextProf.slice(PROF.length) : null, o?.label);
    }
    const nextSkills = next.filter((v) => v.startsWith(SKILL)).map((v) => v.slice(SKILL.length));
    if (nextSkills.join() !== skills.join()) {
      const labels: Record<string, string> = {};
      for (const o of opts) if (o.value.startsWith(SKILL)) labels[o.value.slice(SKILL.length)] = o.label;
      onSkills(nextSkills, labels);
    }
  };

  const chip = (o: ComboOption) => {
    const isProf = o.value.startsWith(PROF);
    const remove = () => onChange(value.filter((v) => v !== o.value), selected.filter((x) => x.value !== o.value));
    return (
      <span
        data-testid={isProf ? "query-chip-profession" : "query-chip-skill"}
        className={cn(
          "fsp-chip-in inline-flex h-7 max-w-full items-center gap-1 rounded-md border pl-2 pr-0.5 font-mono text-[12.5px] font-medium",
          isProf ? "border-brand bg-brand text-on-brand" : "border-tint-200 bg-tint-50 text-chip-fg",
        )}
      >
        <span className="truncate">{o.label}</span>
        <button
          type="button"
          tabIndex={-1}
          data-remove
          aria-label={`Убрать «${o.label}»`}
          onMouseDown={(e) => e.preventDefault()}
          onClick={remove}
          className={cn("inline-flex size-6 items-center justify-center rounded-sm", isProf ? "hover:bg-brand-deep" : "text-muted hover:bg-tint-100 hover:text-ink")}
        >
          <X aria-hidden className="size-3.5" />
        </button>
      </span>
    );
  };

  return (
    <div className={cn("relative", className)}>
      <SearchIcon aria-hidden className="pointer-events-none absolute left-4 top-4 z-10 size-5 text-brand-fg" />
      <Combobox
        multiple
        value={value}
        selectedOptions={selected}
        onChange={onChange}
        loadOptions={loadOptions}
        renderChip={chip}
        placeholder={T.queryPlaceholder}
        emptyText={T.queryEmpty}
        aria-label={T.queryLabel}
        data-testid="match-query"
        debounceMs={150}
        className="min-h-14 border-brand-mid py-2.5 pl-12 text-16"
      />
      <p className="mt-1.5 text-12 text-muted" aria-live="polite">
        {parsing ? T.parsing : T.queryHint}
      </p>
    </div>
  );
}
