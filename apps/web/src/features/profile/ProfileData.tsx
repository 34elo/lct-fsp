import { Badge, BuildLog, Button, Field, FieldInput, FspProtocol, Lbl, Num, Panel, PanelCap, StatusTag, formatRub, type FspResult } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { getGetProfileCandidatesMeProfileGetQueryKey, usePatchProfileCandidatesMeProfilePatch } from "@/api/endpoints/candidates/candidates";
import { useConfirmResumeCandidatesMeResumesResumeIdConfirmPost, useUploadResumeCandidatesMeResumesPost } from "@/api/endpoints/resumes/resumes";
import type { CandidateProfile, ParsedResume, ProfileIn, ResumeEducation, ResumeExperience } from "@/api/model";
import { ErrorNote } from "@/features/auth/ui";
import { FspLinkPanel } from "@/features/fsp/FspLinkPanel";
import { stageLines, useResumeJob } from "@/features/onboarding/useResumeJob";
import { validateContacts } from "@/features/profile/ProfileEdit";
import { Gloss } from "@/shared/Gloss";
import { formatsText } from "./home-model";
import { DATA, DISCIPLINE_LABEL, FSP_LEVEL_LABEL, PROFILE, RANK_LABEL, T, TEAM_ROLE_LABEL, roleLabel } from "./text";

const MAX_BYTES = 10 * 1024 * 1024;
const LINK_RE = /^https?:\/\/\S+$/;
const MONTH_RE = /^\d{4}-\d{2}$/;

/** Значения формы «Данные»: одни и те же поля для ручной правки и черновика из резюме. */
export interface DataValues {
  fullName: string;
  email: string;
  phone: string;
  telegram: string;
  links: string[];
  experience: ResumeExperience[];
  education: ResumeEducation[];
}

/** Текущие данные профиля → значения формы. */
export function valuesOf(p: CandidateProfile): DataValues {
  return {
    fullName: p.full_name ?? "",
    email: p.contacts?.email ?? "",
    phone: p.contacts?.phone ?? "",
    telegram: p.contacts?.telegram ?? "",
    links: [...(p.links ?? [])],
    experience: (p.experience ?? []).map((e) => ({ title: e.title, company: e.company, start: e.start, end: e.end, skills: e.skills })),
    education: (p.education ?? []).map((e) => ({ ...e })),
  };
}

/** Черновик из резюме поверх текущих данных: найденное в резюме заменяет поле, пустое — не трогает. */
export function mergeDraft(cur: DataValues, parsed: ParsedResume): DataValues {
  const person = parsed.person ?? {};
  const links = [...cur.links, ...(person.links ?? []).filter((l) => LINK_RE.test(l))];
  return {
    fullName: person.full_name || cur.fullName,
    email: person.email || cur.email,
    phone: person.phone || cur.phone,
    telegram: person.telegram || cur.telegram,
    links: [...new Set(links)].slice(0, 10),
    experience: parsed.experience?.length ? parsed.experience.map((e) => ({ ...e })) : cur.experience,
    education: parsed.education?.length ? parsed.education.map((e) => ({ ...e })) : cur.education,
  };
}

/** Ошибки формы по ключу поля: `email`, `links.0`, `experience.1.start`, `education.0.year_end`. */
export function validateData(v: DataValues): Record<string, string> {
  const err = validateContacts({ email: v.email.trim(), phone: v.phone.trim(), telegram: v.telegram.trim(), months: "" });
  v.links.forEach((l, i) => {
    if (l.trim() && !LINK_RE.test(l.trim())) err[`links.${i}`] = DATA.invalidLink;
  });
  v.experience.forEach((e, i) => {
    for (const k of ["start", "end"] as const) if (e[k] && !MONTH_RE.test(e[k] ?? "")) err[`experience.${i}.${k}`] = DATA.invalidMonth;
  });
  v.education.forEach((e, i) => {
    if (e.year_end != null && (e.year_end < 1950 || e.year_end > 2100)) err[`education.${i}.year_end`] = DATA.invalidYear;
  });
  return err;
}

const yearOf = (v?: string | null) => (v ? v.slice(0, 4) : "");
const span = (start?: string | null, end?: string | null) => [yearOf(start), end ? yearOf(end) : start ? DATA.present : ""].filter(Boolean).join(" — ");
const hostOf = (url: string) => {
  try {
    return new URL(url).host.replace(/^www\./, "");
  } catch {
    return url;
  }
};

/** Строка данных: подпись слева, значение справа — один формат для всех разделов вкладки. */
function Row({ label, children, testid }: { label: ReactNode; children: ReactNode; testid?: string }) {
  return (
    <div className="flex min-h-11 flex-col gap-0.5 border-t border-hairline py-2.5 first:border-t-0 first:pt-0 sm:flex-row sm:items-center sm:gap-3" data-testid={testid}>
      <Lbl className="flex-none sm:w-32">{label}</Lbl>
      <div className="min-w-0 flex-1 break-words text-14">{children}</div>
    </div>
  );
}

function Card({ title, testid, aside, children }: { title: string; testid: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <Panel role="region" aria-label={title} data-testid={testid} className="flex flex-col gap-3">
      <PanelCap title={title} aside={aside} className="mb-0" />
      {children}
    </Panel>
  );
}

const none = <span className="text-muted">{DATA.notSet}</span>;

/* ---------- Просмотр ---------- */

function View({ p }: { p: CandidateProfile }) {
  const v = valuesOf(p);
  const pref = p.preferences;
  const formats = formatsText(pref.formats ?? []);
  const roles = (p.desired_roles ?? []).map(roleLabel);
  const unreachable = !v.fullName || !(v.email || v.phone || v.telegram);
  return (
    <>
      {unreachable && (
        <p role="alert" data-testid="profile-hidden-warning" className="m-0 rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          {DATA.hiddenWarning}
        </p>
      )}
      <Card title={DATA.personal} testid="profile-data-personal">
        <div>
          <Row label={DATA.fullName} testid="profile-data-name">
            <span className="flex flex-col gap-0.5">
              {v.fullName || none}
              <span className="text-12 text-muted">
                {p.visibility.full_name ? DATA.nameOpen : DATA.nameHidden}{" "}
                <Link to="/settings?tab=privacy" className="font-semibold text-brand-fg">
                  {DATA.privacyLink}
                </Link>
              </span>
            </span>
          </Row>
          <Row label={DATA.email}>{v.email || none}</Row>
          <Row label={DATA.phone}>{v.phone || none}</Row>
          <Row label={DATA.telegram}>{v.telegram || none}</Row>
        </div>
        <p className="text-12 text-muted">{DATA.contactsNote}</p>
      </Card>
      <Card title={DATA.experience} testid="profile-data-experience" aside={<Num className="text-12 text-muted">{v.experience.length}</Num>}>
        {v.experience.length ? (
          <div>
            {v.experience.map((e, i) => (
              <Row key={`${e.title}-${i}`} label={span(e.start, e.end) || "—"}>
                <span className="font-semibold">{e.title || "—"}</span>
                {e.company && <span className="text-muted"> · {e.company}</span>}
              </Row>
            ))}
          </div>
        ) : (
          <p className="text-14 text-muted">{DATA.noExperience}</p>
        )}
      </Card>
      <Card title={DATA.education} testid="profile-data-education" aside={<Num className="text-12 text-muted">{v.education.length}</Num>}>
        {v.education.length ? (
          <div>
            {v.education.map((e, i) => (
              <Row key={`${e.institution}-${i}`} label={e.year_end ?? "—"}>
                <span className="font-semibold">{e.institution || "—"}</span>
                {(e.degree || e.field) && <span className="text-muted"> · {[e.degree, e.field].filter(Boolean).join(", ")}</span>}
              </Row>
            ))}
          </div>
        ) : (
          <p className="text-14 text-muted">{DATA.noEducation}</p>
        )}
      </Card>
      <Card title={DATA.links} testid="profile-data-links" aside={<Num className="text-12 text-muted">{v.links.length}</Num>}>
        {v.links.length ? (
          <div>
            {v.links.map((l) => (
              <Row key={l} label={hostOf(l)}>
                <a href={l} target="_blank" rel="noopener noreferrer nofollow" className="font-semibold text-brand-fg underline-offset-2 hover:underline">
                  {l}
                </a>
              </Row>
            ))}
          </div>
        ) : (
          <p className="text-14 text-muted">{DATA.noLinks}</p>
        )}
      </Card>
      <Card title={DATA.preferences} testid="profile-data-preferences">
        <div>
          <Row label={PROFILE.city}>{pref.city ? <Num className="text-14">{pref.city}</Num> : none}</Row>
          <Row label={PROFILE.salary}>{pref.salary_min != null ? <Num className="text-14">{PROFILE.salaryFrom(formatRub(pref.salary_min))}</Num> : none}</Row>
          <Row label={PROFILE.format}>{formats ? formats.toLowerCase() : none}</Row>
          <Row label={PROFILE.experience}>{p.experience_months != null ? PROFILE.experienceMonths(p.experience_months) : none}</Row>
          {roles.length > 0 && <Row label={PROFILE.roles}>{roles.join(", ")}</Row>}
        </div>
        <Link to="/me/profile/edit" data-testid="profile-edit-link" className="inline-flex min-h-11 items-center self-start font-semibold text-brand-fg">
          {DATA.preferencesEdit}
        </Link>
      </Card>
    </>
  );
}

/* ---------- Правка (вручную или черновик из резюме) ---------- */

function Form({ initial, draft, skillsFound, pending, error, onCancel, onSave }: {
  initial: DataValues;
  draft: boolean;
  skillsFound: number;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSave: (v: DataValues) => void;
}) {
  const [v, setV] = useState(initial);
  const [submitted, setSubmitted] = useState(false);
  const errors = validateData(v);
  const show = (k: string) => (submitted ? errors[k] : undefined);
  const setExp = (i: number, patch: Partial<ResumeExperience>) => setV((x) => ({ ...x, experience: x.experience.map((e, j) => (j === i ? { ...e, ...patch } : e)) }));
  const setEdu = (i: number, patch: Partial<ResumeEducation>) => setV((x) => ({ ...x, education: x.education.map((e, j) => (j === i ? { ...e, ...patch } : e)) }));

  function submit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    if (Object.keys(errors).length) return;
    onSave(v);
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4" data-testid="profile-data-form" data-draft={draft || undefined}>
      {draft && (
        <Panel className="flex flex-col gap-1.5 border-brand bg-brand-tint" role="status" data-testid="profile-data-draft">
          <b className="text-14">{DATA.draftTitle}</b>
          <p className="text-13">{DATA.draftHint}</p>
          {skillsFound > 0 && <p className="text-13">{DATA.draftSkills(skillsFound)}</p>}
        </Panel>
      )}
      <Card title={DATA.personal} testid="profile-data-personal-form">
        <Field label={DATA.fullName}>
          <FieldInput autoComplete="name" maxLength={120} value={v.fullName} onChange={(e) => setV({ ...v, fullName: e.target.value })} data-testid="profile-data-fullname" />
        </Field>
        <p className="-mt-1 text-12 text-muted">{DATA.nameHidden}</p>
        <div className="grid gap-3 md:grid-cols-3">
          <Field label={DATA.email} error={show("email")}>
            <FieldInput type="email" autoComplete="email" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} data-testid="profile-data-email" />
          </Field>
          <Field label={DATA.phone} error={show("phone")}>
            <FieldInput type="tel" autoComplete="tel" value={v.phone} onChange={(e) => setV({ ...v, phone: e.target.value })} data-testid="profile-data-phone" />
          </Field>
          <Field label={DATA.telegram} error={show("telegram")}>
            <FieldInput value={v.telegram} placeholder="@username" onChange={(e) => setV({ ...v, telegram: e.target.value })} data-testid="profile-data-telegram" />
          </Field>
        </div>
      </Card>

      <Card title={DATA.experience} testid="profile-data-experience-form">
        {!draft ? (
          <p className="text-13 text-muted">{DATA.fromResumeOnly}</p>
        ) : (
          <>
            {v.experience.map((e, i) => (
              <fieldset key={i} className="grid gap-3 border-t border-hairline pt-3 first-of-type:border-t-0 first-of-type:pt-0 md:grid-cols-2" data-testid={`profile-data-exp-${i}`}>
                <Field label={DATA.position}>
                  <FieldInput value={e.title ?? ""} onChange={(x) => setExp(i, { title: x.target.value || null })} />
                </Field>
                <Field label={DATA.company}>
                  <FieldInput value={e.company ?? ""} onChange={(x) => setExp(i, { company: x.target.value || null })} />
                </Field>
                <Field label={DATA.start} error={show(`experience.${i}.start`)}>
                  <FieldInput inputMode="numeric" placeholder="2023-09" value={e.start ?? ""} onChange={(x) => setExp(i, { start: x.target.value || null })} />
                </Field>
                <Field label={DATA.end} error={show(`experience.${i}.end`)}>
                  <FieldInput inputMode="numeric" placeholder="2025-06" value={e.end ?? ""} onChange={(x) => setExp(i, { end: x.target.value || null })} />
                </Field>
                <Button type="button" variant="ghost" size="sm" className="justify-self-start" onClick={() => setV({ ...v, experience: v.experience.filter((_, j) => j !== i) })}>
                  {DATA.remove}
                </Button>
              </fieldset>
            ))}
            <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setV({ ...v, experience: [...v.experience, { title: null, company: null, start: null, end: null, skills: [] }] })} data-testid="profile-data-exp-add">
              {DATA.addExperience}
            </Button>
          </>
        )}
      </Card>

      <Card title={DATA.education} testid="profile-data-education-form">
        {!draft ? (
          <p className="text-13 text-muted">{DATA.fromResumeOnly}</p>
        ) : (
          <>
            {v.education.map((e, i) => (
              <fieldset key={i} className="grid gap-3 border-t border-hairline pt-3 first-of-type:border-t-0 first-of-type:pt-0 md:grid-cols-2" data-testid={`profile-data-edu-${i}`}>
                <Field label={DATA.institution}>
                  <FieldInput value={e.institution ?? ""} onChange={(x) => setEdu(i, { institution: x.target.value || null })} />
                </Field>
                <Field label={DATA.yearEnd} error={show(`education.${i}.year_end`)}>
                  <FieldInput inputMode="numeric" maxLength={4} value={e.year_end ?? ""} onChange={(x) => setEdu(i, { year_end: x.target.value.replace(/\D/g, "") ? Number(x.target.value.replace(/\D/g, "")) : null })} />
                </Field>
                <Field label={DATA.degree}>
                  <FieldInput value={e.degree ?? ""} onChange={(x) => setEdu(i, { degree: x.target.value || null })} />
                </Field>
                <Field label={DATA.field}>
                  <FieldInput value={e.field ?? ""} onChange={(x) => setEdu(i, { field: x.target.value || null })} />
                </Field>
                <Button type="button" variant="ghost" size="sm" className="justify-self-start" onClick={() => setV({ ...v, education: v.education.filter((_, j) => j !== i) })}>
                  {DATA.remove}
                </Button>
              </fieldset>
            ))}
            <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setV({ ...v, education: [...v.education, { institution: null, degree: null, field: null, year_end: null }] })}>
              {DATA.addEducation}
            </Button>
          </>
        )}
      </Card>

      <Card title={DATA.links} testid="profile-data-links-form">
        {v.links.map((l, i) => (
          <div key={i} className="flex items-end gap-2">
            <Field label={DATA.link(i + 1)} error={show(`links.${i}`)} className="min-w-0 flex-1">
              <FieldInput type="url" inputMode="url" placeholder="https://github.com/…" value={l} onChange={(e) => setV({ ...v, links: v.links.map((x, j) => (j === i ? e.target.value : x)) })} data-testid={`profile-data-link-${i}`} />
            </Field>
            <Button type="button" variant="ghost" size="sm" className="mb-0.5" onClick={() => setV({ ...v, links: v.links.filter((_, j) => j !== i) })}>
              {DATA.remove}
            </Button>
          </div>
        ))}
        {v.links.length < 10 && (
          <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setV({ ...v, links: [...v.links, ""] })} data-testid="profile-data-link-add">
            {DATA.addLink}
          </Button>
        )}
      </Card>

      {error && <ErrorNote data-testid="profile-data-error">{error}</ErrorNote>}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button type="submit" size="lg" loading={pending} data-testid="profile-data-save">
          {pending ? DATA.saving : DATA.save}
        </Button>
        <Button type="button" variant="ghost" size="lg" onClick={onCancel} data-testid="profile-data-cancel">
          {DATA.cancel}
        </Button>
      </div>
    </form>
  );
}

/* ---------- ФСП ---------- */

function FspCard({ p, imported }: { p: CandidateProfile; imported: boolean }) {
  const items = p.fsp?.achievements ?? [];
  const ranks = p.fsp?.ranks ?? [];
  const placed: FspResult[] = items
    .filter((a) => a.place != null)
    .map((a) => ({
      discipline: FSP_LEVEL_LABEL[a.level] ?? a.level,
      tournament: a.title,
      place: a.place as number,
      total: a.of ?? undefined,
      role: a.team_role ? (TEAM_ROLE_LABEL[a.team_role] ?? a.team_role) : undefined,
      year: a.year,
    }));
  const unplaced = items.filter((a) => a.place == null);
  const linked = Boolean(p.fsp?.verified);
  return (
    <Panel role="region" aria-label="Достижения ФСП" data-testid="profile-fsp" className="flex flex-col gap-3">
      <PanelCap
        title={
          <Gloss k="fspRelevance">
            <span className="font-mono text-16 font-semibold">{PROFILE.fspTitle}</span>
          </Gloss>
        }
        aside={<StatusTag state={linked ? "ok" : "claimed"}>{linked ? PROFILE.fspLinked : PROFILE.fspNotLinked}</StatusTag>}
        className="mb-0"
      />
      {items.length === 0 && ranks.length === 0 ? (
        <p className="text-14 text-muted">{T.fspEmpty}</p>
      ) : (
        <>
          {placed.length > 0 && <FspProtocol results={placed} />}
          {unplaced.length > 0 && (
            <ul className="flex flex-col gap-1">
              {unplaced.map((a) => (
                <li key={a.fact_id} className="text-14">
                  {a.title} <span className="font-mono text-12 text-muted">· {a.year}</span>
                </li>
              ))}
            </ul>
          )}
          {ranks.length > 0 && (
            <ul className="flex flex-wrap gap-2 border-t border-hairline pt-3">
              {ranks.map((r) => (
                <li key={r.discipline}>
                  <Badge>
                    {RANK_LABEL[r.rank] ?? r.rank} · {DISCIPLINE_LABEL[r.discipline] ?? r.discipline}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      {imported && (
        <p role="status" className="text-14 font-semibold text-brand-fg">
          {T.fspImported}
        </p>
      )}
      <FspLinkPanel />
    </Panel>
  );
}

/* ---------- Вкладка ---------- */

type Mode = "view" | "edit" | "draft";

/**
 * Вкладка «Данные» профиля: ФИО, контакты, опыт, образование, ссылки в одном формате строк,
 * пожелания и отдельная карточка ФСП. «Заполнить из резюме» загружает файл, разбор кладёт черновик в те же
 * поля; сохранение — `PATCH /candidates/me/profile` (ФИО, контакты, ссылки) и подтверждение резюме (опыт,
 * образование, навыки). Незавершённый черновик живёт в `resume_draft_id` и виден после перезагрузки.
 */
export function DataTab({ p, imported }: { p: CandidateProfile; imported: boolean }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const upload = useUploadResumeCandidatesMeResumesPost();
  const patch = usePatchProfileCandidatesMeProfilePatch();
  const confirm = useConfirmResumeCandidatesMeResumesResumeIdConfirmPost();
  const [local, setLocal] = useState<{ resumeId: string; jobId: string } | null>(null);
  const [mode, setMode] = useState<Mode>("view");
  const [applied, setApplied] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const draftId = local?.resumeId ?? p.resume_draft_id ?? null;
  const job = useResumeJob(draftId, local?.jobId ?? null);
  const status = job.resume?.status;
  const parsed = status === "parsed" ? (job.resume?.parsed ?? null) : null;

  // Разбор готов — черновик сам открывается в полях формы (один раз на резюме).
  useEffect(() => {
    if (parsed && draftId && applied !== draftId) {
      setApplied(draftId);
      setSaved(false);
      setMode("draft");
    }
  }, [parsed, draftId, applied]);

  async function pick(file: File | undefined) {
    if (!file) return;
    setFileError(null);
    if (file.size > MAX_BYTES) return setFileError("Файл больше 10 МБ.");
    if (!/\.(pdf|docx)$/i.test(file.name)) return setFileError("Подходят только PDF и DOCX.");
    try {
      const res = await upload.mutateAsync({ data: { file } });
      const body = res.data as { resume_id: string; job_id: string };
      job.reset();
      setLocal({ resumeId: body.resume_id, jobId: body.job_id });
    } catch {
      setFileError("Не удалось загрузить файл, попробуйте позже.");
    }
  }

  async function save(v: DataValues) {
    setSaveError(null);
    const contacts = v.email.trim() || v.phone.trim() || v.telegram.trim() ? { email: v.email.trim() || null, phone: v.phone.trim() || null, telegram: v.telegram.trim() || null } : null;
    const body: ProfileIn = { full_name: v.fullName.trim() || null, contacts, links: v.links.map((l) => l.trim()).filter(Boolean) };
    try {
      await patch.mutateAsync({ data: body });
      if (mode === "draft" && draftId) {
        await confirm.mutateAsync({ resumeId: draftId, data: { edits: { experience: v.experience, education: v.education } } });
        setLocal(null);
      }
      await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
      setMode("view");
      setSaved(true);
    } catch {
      setSaveError(DATA.saveError);
    }
  }

  const busy = upload.isPending || status === "queued" || status === "parsing" || (!!draftId && !job.resume && !job.isError);
  const initial = mode === "draft" && parsed ? mergeDraft(valuesOf(p), parsed) : valuesOf(p);

  return (
    <div className="flex flex-col gap-4" data-testid="profile-data">
      <Panel className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between" data-testid="profile-data-actions">
        <p className="text-13 text-muted">{DATA.fromResumeHint}</p>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            ref={input}
            type="file"
            accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            aria-label={DATA.resumeFile}
            className="hidden"
            data-testid="profile-data-file"
            onChange={(e) => {
              void pick(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <Button size="lg" loading={busy} disabled={mode !== "view" && mode !== "edit"} onClick={() => input.current?.click()} data-testid="profile-data-from-resume">
            {upload.isPending ? DATA.uploading : busy ? DATA.parsing : DATA.fromResume}
          </Button>
          {mode === "view" && (
            <Button variant="outline" size="lg" onClick={() => {
                setSaved(false);
                setMode(parsed ? "draft" : "edit");
              }} data-testid="profile-data-edit">
              {parsed ? DATA.draftReview : DATA.edit}
            </Button>
          )}
        </div>
      </Panel>
      {fileError && <ErrorNote data-testid="profile-data-file-error">{fileError}</ErrorNote>}
      {draftId && (busy || status === "failed") && mode !== "draft" && (
        <div className="flex flex-col gap-2" data-testid="profile-data-parsing">
          <BuildLog title="разбор резюме" lines={status === "failed" ? [...stageLines(job.stages, status), { id: "fail", text: DATA.draftFailed, state: "fail" }] : stageLines(job.stages, status)} />
        </div>
      )}
      {saved && mode === "view" && (
        <p role="status" className="rounded-lg bg-tint-50 px-3 py-2 text-14" data-testid="profile-data-saved">
          {DATA.saved}
        </p>
      )}
      {mode === "view" ? (
        <View p={p} />
      ) : (
        <Form
          key={`${mode}-${draftId ?? ""}`}
          initial={initial}
          draft={mode === "draft"}
          skillsFound={parsed ? (parsed.skills?.length ?? 0) + (parsed.unknown_skills?.length ?? 0) : 0}
          pending={patch.isPending || confirm.isPending}
          error={saveError}
          onCancel={() => setMode("view")}
          onSave={(v) => void save(v)}
        />
      )}
      <FspCard p={p} imported={imported} />
    </div>
  );
}
