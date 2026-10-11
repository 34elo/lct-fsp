import { Button, Checkbox, Chips, EmptyState, Field, FieldInput, Num, Panel, PanelCap, Select, SKILL_TYPE_LABEL, SkillTag, Tag, cn, dotsText } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getGetProfileCandidatesMeProfileGetQueryKey, usePatchProfileCandidatesMeProfilePatch } from "@/api/endpoints/candidates/candidates";
import type { CandidateProfile, SkillWithTrust } from "@/api/model";
import { dayMonth } from "./home-model";
import { NO_FILTER, SKILLS_TOP, filterSkills, isFiltered, skillTypes, toggleHidden, trustOf, type SkillFilter, type SkillState } from "./skills-model";
import { PROFILE, SKILLS, SOURCE_TAG, T } from "./text";

function skillTags(s: SkillWithTrust): string[] {
  if (s.claimed_only) return [s.sources.includes("resume") ? PROFILE.claimedInResume : PROFILE.claimedSelf];
  const testEv = s.top_evidence?.find((e) => e.source === "test");
  const tags = ["test", "fsp", "task", "resume"].filter((k) => s.sources.includes(k)).map((k) => (k === "test" ? PROFILE.testTag(dayMonth(testEv?.observed_at)) : SOURCE_TAG[k]));
  if (!tags.length) tags.push(s.derived_from ? PROFILE.derived : PROFILE.claimedSelf);
  return tags;
}

function SkillRow({ s, hidden, busy, onToggle }: { s: SkillWithTrust; hidden: boolean; busy: boolean; onToggle: () => void }) {
  const name = s.skill.name;
  return (
    <li className="flex items-center gap-2 border-t border-hairline first:border-t-0" data-testid={`profile-skill-${s.skill.slug}`} data-hidden={hidden || undefined}>
      <Link to={`/me/skills/${encodeURIComponent(s.skill.slug)}`} aria-label={PROFILE.skillLink(name)} className={cn("flex min-h-11 min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1 py-2", hidden && "opacity-60")}>
        <SkillTag name={name} state={s.claimed_only ? "claimed" : "confirmed"} className="min-w-24" />
        <span aria-label={`доверие ${trustOf(s)} из 4`} className="font-mono text-12 font-semibold tracking-[1px] text-brand-fg">
          {dotsText(trustOf(s))}
        </span>
        <Chips className="min-w-0 flex-1 md:justify-end">
          {hidden && <Tag>{SKILLS.hiddenTag}</Tag>}
          {skillTags(s).map((t) => (
            <Tag key={t}>{t}</Tag>
          ))}
        </Chips>
      </Link>
      <Button
        variant="ghost"
        size="sm"
        disabled={busy}
        aria-label={hidden ? SKILLS.unhide(name) : SKILLS.hide(name)}
        aria-pressed={hidden}
        onClick={onToggle}
        data-testid={`profile-skill-hide-${s.skill.slug}`}
        className="flex-none"
      >
        {hidden ? SKILLS.unhideShort : SKILLS.hideShort}
      </Button>
    </li>
  );
}

const STATES: SkillState[] = ["all", "confirmed", "claimed"];

/**
 * Вкладка «Навыки» профиля: поиск, фильтры (тип, доверие, заявлено/подтверждено), скрытие навыка
 * от компаний (`hidden_skills`), по умолчанию первые 15 сильнейших. Блоков про грейд здесь нет — они в «Обзоре».
 */
export function SkillsTab({ p }: { p: CandidateProfile }) {
  const qc = useQueryClient();
  const patch = usePatchProfileCandidatesMeProfilePatch();
  const [f, setF] = useState<SkillFilter>(NO_FILTER);
  const [all, setAll] = useState(false);
  const [error, setError] = useState(false);
  const skills = useMemo(() => p.skills ?? [], [p.skills]);
  const hiddenList = p.hidden_skills ?? [];
  const hidden = useMemo(() => new Set(p.hidden_skills ?? []), [p.hidden_skills]);
  const types = useMemo(() => skillTypes(skills), [skills]);
  const found = filterSkills(skills, hidden, f);
  const shown = all ? found : found.slice(0, SKILLS_TOP);
  const hiddenCount = skills.filter((s) => hidden.has(s.skill.slug)).length;
  const set = (patch: Partial<SkillFilter>) => setF((x) => ({ ...x, ...patch }));

  async function toggle(slug: string) {
    setError(false);
    try {
      await patch.mutateAsync({ data: { hidden_skills: toggleHidden(hiddenList, slug) } });
      await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
    } catch {
      setError(true);
    }
  }

  if (!skills.length)
    return (
      <Panel data-testid="profile-skills">
        <EmptyState className="min-h-[200px]" title={PROFILE.empty} description={T.skillsEmpty} />
      </Panel>
    );

  return (
    <Panel role="region" aria-label={SKILLS.title} className="flex flex-col gap-3" data-testid="profile-skills">
      <PanelCap title={SKILLS.title} aside={<Num className="text-12 text-muted">{skills.length}</Num>} className="mb-0" />
      <p className="text-13 text-muted">{T.skillsHint}</p>
      <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]" data-testid="profile-skills-filters">
        <Field label={SKILLS.search}>
          <FieldInput type="search" value={f.q} placeholder={SKILLS.searchPlaceholder} onChange={(e) => set({ q: e.target.value })} data-testid="profile-skills-search" />
        </Field>
        <Field label={SKILLS.type}>
          <Select
            value={f.type ?? ""}
            onChange={(v) => set({ type: v || null })}
            options={[{ value: "", label: SKILLS.typeAll }, ...types.map((t) => ({ value: t, label: SKILL_TYPE_LABEL[t] ?? t }))]}
            aria-label={SKILLS.type}
            data-testid="profile-skills-type"
          />
        </Field>
        <Field label={SKILLS.trust}>
          <Select
            value={String(f.trust)}
            onChange={(v) => set({ trust: Number(v ?? 0) })}
            options={[{ value: "0", label: SKILLS.trustAny }, ...[1, 2, 3, 4].map((n) => ({ value: String(n), label: SKILLS.trustFrom(n) }))]}
            aria-label={SKILLS.trust}
            data-testid="profile-skills-trust"
          />
        </Field>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label={SKILLS.state} className="flex flex-wrap gap-1.5">
          {STATES.map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={f.state === k}
              onClick={() => set({ state: k })}
              data-testid={`profile-skills-state-${k}`}
              className={cn(
                "min-h-11 rounded-full border px-3.5 text-13 font-semibold",
                f.state === k ? "border-brand bg-brand-tint text-brand-fg" : "border-hairline bg-card text-ink hover:border-brand-mid",
              )}
            >
              {SKILLS.states[k]}
            </button>
          ))}
        </div>
        {hiddenCount > 0 && (
          <label className="flex min-h-11 items-center gap-2 text-13">
            <Checkbox checked={f.showHidden} onCheckedChange={(v) => set({ showHidden: v === true })} data-testid="profile-skills-show-hidden" />
            {SKILLS.showHidden(hiddenCount)}
          </label>
        )}
      </div>
      {error && (
        <p role="alert" className="text-13 text-error">
          {SKILLS.hideError}
        </p>
      )}
      {found.length === 0 ? (
        <EmptyState
          className="min-h-[160px]"
          title={SKILLS.nothing}
          description={SKILLS.nothingHint}
          action={
            <Button variant="outline" onClick={() => setF(NO_FILTER)} data-testid="profile-skills-reset">
              {SKILLS.reset}
            </Button>
          }
        />
      ) : (
        <>
          <ul className="flex flex-col" data-testid="profile-skills-list">
            {shown.map((s) => (
              <SkillRow key={s.skill.slug} s={s} hidden={hidden.has(s.skill.slug)} busy={patch.isPending} onToggle={() => void toggle(s.skill.slug)} />
            ))}
          </ul>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-hairline pt-3">
            <span className="text-13 text-muted" data-testid="profile-skills-count">
              {SKILLS.shown(shown.length, found.length)}
            </span>
            {found.length > SKILLS_TOP && (
              <Button variant="ghost" size="sm" onClick={() => setAll((x) => !x)} data-testid="profile-skills-all">
                {all ? SKILLS.showTop : SKILLS.showAll(found.length)}
              </Button>
            )}
            {isFiltered(f) && (
              <Button variant="ghost" size="sm" onClick={() => setF({ ...NO_FILTER, showHidden: f.showHidden })}>
                {SKILLS.reset}
              </Button>
            )}
          </div>
          <p className="text-12 text-muted">{SKILLS.hideHint}</p>
        </>
      )}
    </Panel>
  );
}
