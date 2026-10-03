import { useState } from "react";

import type { ParsedResume, ParsedResumeEdits, ResumeEducation, ResumeExperience } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { warningText } from "@/features/onboarding/text";
import { SkillChip } from "@/shared/brand";
import { Button } from "@/shared/ui/button";

function months(n: number) {
  const y = Math.floor(n / 12);
  const m = n % 12;
  return [y ? `${y} г.` : "", m ? `${m} мес.` : ""].filter(Boolean).join(" ") || "—";
}

/** Строка, которую можно поправить на месте: клик открывает поля, «Сохранить» возвращает значения. */
function EditableRow({
  label,
  fields,
  onSave,
  children,
}: {
  label: string;
  fields: { key: string; label: string; value: string }[];
  onSave: (v: Record<string, string>) => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  if (!open) {
    return (
      <button
        type="button"
        aria-label={`Поправить: ${label}`}
        onClick={() => {
          setDraft(Object.fromEntries(fields.map((f) => [f.key, f.value])));
          setOpen(true);
        }}
        className="w-full rounded-lg border border-hairline bg-card p-3 text-left hover:bg-tint-50"
      >
        {children}
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-brand bg-card p-3">
      {fields.map((f) => (
        <label key={f.key} className="flex flex-col gap-1 text-sm">
          <span className="text-muted">{f.label}</span>
          <input
            className={fieldClass}
            value={draft[f.key] ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
          />
        </label>
      ))}
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => {
            onSave(draft);
            setOpen(false);
          }}
        >
          Сохранить
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Отмена
        </Button>
      </div>
    </div>
  );
}

/**
 * «Вот что я понял»: разобранное резюме с правкой на месте. Навыки из резюме получают одну точку
 * (заявлено, не подтверждено), `unknown_skills` — пометку «новый».
 */
export function Understood({
  parsed,
  onConfirm,
  pending,
  error,
  onSkip,
}: {
  parsed: ParsedResume;
  onConfirm: (edits: ParsedResumeEdits) => void;
  pending: boolean;
  error: string | null;
  onSkip: () => void;
}) {
  const [experience, setExperience] = useState<ResumeExperience[]>(parsed.experience ?? []);
  const [education, setEducation] = useState<ResumeEducation[]>(parsed.education ?? []);
  const [touched, setTouched] = useState({ experience: false, education: false });
  const [removed, setRemoved] = useState<string[]>([]);
  const [added, setAdded] = useState<string[]>([]);
  const [draft, setDraft] = useState("");

  const skills = (parsed.skills ?? []).filter((s) => !s.slug || !removed.includes(s.slug));
  const warnings = (parsed.warnings ?? []).map(warningText).filter((w): w is string => !!w);

  function submit() {
    onConfirm({
      remove_skills: removed,
      add_skills: added,
      ...(touched.experience ? { experience } : {}),
      ...(touched.education ? { education } : {}),
    });
  }

  function addSkill() {
    const slug = draft.trim().toLowerCase();
    if (slug && !added.includes(slug)) setAdded([...added, slug]);
    setDraft("");
  }

  return (
    <section aria-labelledby="understood-h" className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h2 id="understood-h" className="text-xl font-bold">Вот что я понял</h2>
        <p className="text-sm text-muted">Проверьте, всё ли верно. Нажмите на строку, чтобы поправить.</p>
      </header>

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-muted">
          Опыт · {months(parsed.total_experience_months ?? 0)}
        </h3>
        {experience.length === 0 && <p className="text-sm text-muted">Мест работы не нашли.</p>}
        {experience.map((e, i) => (
          <EditableRow
            key={i}
            label={e.title ?? e.company ?? `место работы ${i + 1}`}
            fields={[
              { key: "title", label: "Должность", value: e.title ?? "" },
              { key: "company", label: "Компания", value: e.company ?? "" },
            ]}
            onSave={(v) => {
              setExperience((xs) => xs.map((x, j) => (j === i ? { ...x, title: v.title || null, company: v.company || null } : x)));
              setTouched((t) => ({ ...t, experience: true }));
            }}
          >
            <p className="font-semibold">{e.title || "Должность не указана"}</p>
            <p className="text-sm text-muted">
              {[e.company, e.start && `${e.start} — ${e.end ?? "сейчас"}`].filter(Boolean).join(" · ") || "Данных мало"}
            </p>
          </EditableRow>
        ))}
      </div>

      {(education.length > 0) && (
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-muted">Образование</h3>
          {education.map((e, i) => (
            <EditableRow
              key={i}
              label={e.field ?? e.institution ?? `образование ${i + 1}`}
              fields={[
                { key: "institution", label: "Учебное заведение", value: e.institution ?? "" },
                { key: "field", label: "Направление", value: e.field ?? "" },
              ]}
              onSave={(v) => {
                setEducation((xs) => xs.map((x, j) => (j === i ? { ...x, institution: v.institution || null, field: v.field || null } : x)));
                setTouched((t) => ({ ...t, education: true }));
              }}
            >
              <p className="font-semibold">{e.field || e.degree || "Направление не указано"}</p>
              <p className="text-sm text-muted">
                {[e.institution, e.year_end && `до ${e.year_end}`].filter(Boolean).join(" · ") || "Данных мало"}
              </p>
            </EditableRow>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-muted">Навыки · из резюме, доверие слабое</h3>
        <ul className="flex flex-wrap gap-2">
          {skills.map((s, i) => (
            <li key={`${s.slug ?? s.raw}-${i}`} className="fsp-chip-in flex items-center gap-1" style={{ animationDelay: `${i * 60}ms` }}>
              <SkillChip name={s.raw} level={1} variant="claimed" />
              {s.slug && (
                <button
                  type="button"
                  aria-label={`Убрать навык ${s.raw}`}
                  onClick={() => setRemoved((r) => [...r, s.slug as string])}
                  className="size-6 rounded-md text-muted hover:bg-tint-100"
                >
                  ×
                </button>
              )}
            </li>
          ))}
          {added.map((slug) => (
            <li key={`add-${slug}`} className="fsp-chip-in flex items-center gap-1">
              <SkillChip name={slug} level={1} variant="claimed" />
              <button
                type="button"
                aria-label={`Убрать навык ${slug}`}
                onClick={() => setAdded((a) => a.filter((x) => x !== slug))}
                className="size-6 rounded-md text-muted hover:bg-tint-100"
              >
                ×
              </button>
            </li>
          ))}
          {(parsed.unknown_skills ?? []).map((u) => (
            <li key={`unk-${u}`} className="fsp-chip-in">
              <SkillChip name={u} level={1} variant="provisional" />
            </li>
          ))}
        </ul>
        {(parsed.unknown_skills?.length ?? 0) > 0 && (
          <p className="text-sm text-muted">
            Новые навыки раньше не встречались в справочнике: мы добавим их с пометкой «новый», доверие к ним пока минимальное.
          </p>
        )}
        <div className="flex gap-2">
          <input
            className={fieldClass}
            aria-label="Добавить навык"
            placeholder="Добавить навык, например redis"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addSkill();
              }
            }}
          />
          <Button variant="outline" onClick={addSkill} disabled={!draft.trim()}>
            Добавить
          </Button>
        </div>
      </div>

      {warnings.length > 0 && (
        <ul className="flex flex-col gap-2">
          {warnings.map((w) => (
            <li key={w} className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-fg">
              {w}
            </li>
          ))}
        </ul>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}
      <div className="flex flex-col gap-2">
        <Button size="lg" onClick={submit} disabled={pending}>
          {pending ? "Сохраняем…" : "Всё верно"}
        </Button>
        <Button variant="ghost" onClick={onSkip} disabled={pending}>
          Пропустить
        </Button>
      </div>
    </section>
  );
}
