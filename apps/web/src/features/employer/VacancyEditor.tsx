import { PAGE } from "@/shared/lib/page";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useGetMyCompanyCompaniesMeGet } from "@/api/endpoints/companies/companies";
import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import {
  getGetVacancyVacanciesVacancyIdGetQueryKey,
  getListVacanciesVacanciesGetQueryKey,
  useCloseVacancyVacanciesVacancyIdClosePost,
  useCreateVacancyVacanciesPost,
  useGetVacancyVacanciesVacancyIdGet,
  usePatchVacancyVacanciesVacancyIdPatch,
  usePublishVacancyVacanciesVacancyIdPublishPost,
} from "@/api/endpoints/vacancies/vacancies";
import type { SkillReqIn, VacancyOut } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { GRADE_LABEL, ROLE_LABEL, SIGNAL_LABEL } from "@/features/profile/text";
import { Button, cn, SalaryRangeInput, Select, Skeleton } from "@fsp/ui";

import { EMPLOYMENT_LABEL, FORMAT_LABEL, LEVEL_WORD, QUALITY_HINT, VACANCY_STATUS_LABEL, vacancyErrorText } from "./text";

const GRADES = Object.keys(GRADE_LABEL);
const WIDE_RATIO = 1.6; // api.md: salary_to / salary_from > 1.6
const num = (s: string) => (s.trim() === "" ? null : Math.max(0, Math.round(Number(s.replace(/\s/g, "")))) || null);

interface TaxSkill { slug: string; name: string; kind?: string }

function Dots({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={`Минимальный уровень: ${label}`} className="flex items-center gap-1">
      {[1, 2, 3, 4].map((i) => (
        <button
          key={i}
          type="button"
          role="radio"
          aria-checked={value === i}
          aria-label={`${i} — ${LEVEL_WORD[i]}`}
          onClick={() => onChange(i)}
          className="flex h-9 w-7 items-center justify-center"
        >
          <span className={cn("h-3.5 w-3.5 rounded-full border border-brand-fg", i <= value ? "bg-brand" : "bg-transparent")} />
        </button>
      ))}
      <span className="ml-1 text-xs text-muted">{LEVEL_WORD[value]}</span>
    </div>
  );
}

function Chip({ active, children, ...p }: { active: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={active}
      {...p}
      className={cn("h-9 rounded-lg border px-3 text-sm font-semibold", active ? "border-brand bg-brand text-on-brand" : "border-hairline bg-card hover:bg-tint-50")}
    >
      {children}
    </button>
  );
}

export default function VacancyEditor() {
  const { id = "new" } = useParams();
  const isNew = id === "new";
  const nav = useNavigate();
  const qc = useQueryClient();

  const vq = useGetVacancyVacanciesVacancyIdGet(id, { query: { enabled: !isNew, retry: false } });
  const loaded = vq.data?.status === 200 ? vq.data.data : null;
  const company = useGetMyCompanyCompaniesMeGet({ query: { retry: false } });
  const companyStatus = company.data?.status === 200 ? company.data.data.status : null;
  const taxonomy = useGetTaxonomyTaxonomyGet();
  const taxSkills = useMemo(() => (taxonomy.data?.data as { skills?: TaxSkill[] } | undefined)?.skills ?? [], [taxonomy.data]);
  const nameOf = useMemo(() => new Map(taxSkills.map((s) => [s.slug, s.name])), [taxSkills]);

  const [title, setTitle] = useState("");
  const [role, setRole] = useState("backend");
  const [gradeMin, setGradeMin] = useState("middle");
  const [gradeMax, setGradeMax] = useState("middle_plus");
  const [formats, setFormats] = useState<string[]>(["remote"]);
  const [employment, setEmployment] = useState("full");
  const [city, setCity] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [description, setDescription] = useState("");
  const [qualities, setQualities] = useState<string[]>([]);
  const [skills, setSkills] = useState<SkillReqIn[]>([]);
  const [query, setQuery] = useState("");
  const [touched, setTouched] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const fill = (v: VacancyOut) => {
    setTitle(v.title);
    setRole(v.role);
    setGradeMin(v.grade_min);
    setGradeMax(v.grade_max);
    setFormats(v.formats);
    setEmployment(v.employment_type);
    setCity(v.city ?? "");
    setFrom(String(v.salary_from));
    setTo(String(v.salary_to));
    setDescription(v.description ?? "");
    setQualities(v.important_qualities);
    setSkills(v.skills.map((s) => ({ slug: s.slug, required: s.required, min_level: s.min_level, weight: s.weight })));
  };
  useEffect(() => {
    if (loaded) fill(loaded);
  }, [loaded?.id, loaded?.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const lo = num(from);
  const hi = num(to);
  const salaryError = lo === null || hi === null ? "Вилка обязательна: укажите обе границы." : hi < lo ? "Верхняя граница не может быть меньше нижней." : null;
  const wide = lo !== null && hi !== null && hi >= lo && hi / lo > WIDE_RATIO;
  const gradeError = GRADES.indexOf(gradeMin) > GRADES.indexOf(gradeMax) ? "Минимальный грейд выше максимального." : null;
  const titleError = title.trim().length < 2 ? "Введите название вакансии." : null;
  const formatError = formats.length === 0 ? "Выберите хотя бы один формат." : null;
  const invalid = !!(salaryError || gradeError || titleError || formatError);

  const required = skills.filter((s) => s.required !== false);
  const strictest = required.reduce<SkillReqIn | null>((m, s) => ((s.min_level ?? 2) > (m?.min_level ?? 0) ? s : m), null);
  const nice = skills.filter((s) => s.required === false);
  const setSkill = (slug: string, p: Partial<SkillReqIn>) => setSkills((l) => l.map((s) => (s.slug === slug ? { ...s, ...p } : s)));
  const addSkill = (slug: string, req: boolean) => {
    setSkills((l) => (l.some((s) => s.slug === slug) ? l : [...l, { slug, required: req, min_level: req ? 2 : 1, weight: 1 }]));
    setQuery("");
  };
  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const have = new Set(skills.map((s) => s.slug));
    return taxSkills.filter((s) => !have.has(s.slug) && s.kind !== "soft" && (s.slug.includes(q) || s.name.toLowerCase().includes(q))).slice(0, 8);
  }, [query, taxSkills, skills]);

  const toggle = (list: string[], set: (l: string[]) => void, v: string, max = 99) =>
    set(list.includes(v) ? list.filter((x) => x !== v) : list.length >= max ? list : [...list, v]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: getListVacanciesVacanciesGetQueryKey() });
    if (!isNew) void qc.invalidateQueries({ queryKey: getGetVacancyVacanciesVacancyIdGetQueryKey(id) });
  };
  const create = useCreateVacancyVacanciesPost();
  const patch = usePatchVacancyVacanciesVacancyIdPatch();
  const publish = usePublishVacancyVacanciesVacancyIdPublishPost();
  const close = useCloseVacancyVacanciesVacancyIdClosePost();
  const busy = create.isPending || patch.isPending || publish.isPending || close.isPending;
  const error = create.error ?? patch.error ?? publish.error ?? close.error;

  const body = () => ({
    title: title.trim(),
    role: role as VacancyOut["role"],
    grade_min: gradeMin as VacancyOut["grade_min"],
    grade_max: gradeMax as VacancyOut["grade_max"],
    formats: formats as VacancyOut["formats"],
    employment_type: employment as VacancyOut["employment_type"],
    city: city.trim() || null,
    salary_from: lo ?? 0,
    salary_to: hi ?? 0,
    description: description.trim() || null,
    important_qualities: qualities as VacancyOut["important_qualities"],
    skills,
  });

  /** Сохраняет вакансию и возвращает её id (или null при ошибке). */
  const save = async (): Promise<string | null> => {
    setTouched(true);
    setNote(null);
    if (invalid) return null;
    try {
      if (isNew) {
        const r = await create.mutateAsync({ data: body() });
        refresh();
        return r.status === 201 ? r.data.id : null;
      }
      await patch.mutateAsync({ vacancyId: id, data: body() });
      refresh();
      return id;
    } catch {
      return null;
    }
  };
  const onSave = async (e?: FormEvent) => {
    e?.preventDefault();
    const vid = await save();
    if (!vid) return;
    setNote("Сохранено.");
    if (isNew) nav(`/employer/vacancies/${vid}`, { replace: true });
  };
  const onPublish = async () => {
    if (required.length === 0) return setTouched(true);
    const vid = await save();
    if (!vid) return;
    try {
      await publish.mutateAsync({ vacancyId: vid });
      refresh();
      setNote("Вакансия опубликована.");
      if (isNew) nav(`/employer/vacancies/${vid}`, { replace: true });
    } catch {
      if (isNew) nav(`/employer/vacancies/${vid}`, { replace: true });
    }
  };
  const onClose = async () => {
    try {
      await close.mutateAsync({ vacancyId: id });
      refresh();
      setNote("Вакансия закрыта.");
    } catch {
      /* ошибка показана ниже */
    }
  };

  const status = loaded?.status ?? "draft";
  const closed = status === "closed";
  const noRequired = touched && required.length === 0;
  const SkillRow = (s: SkillReqIn) => (
    <li key={s.slug} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-hairline px-3 py-1">
      <span className="font-mono text-sm font-semibold">{nameOf.get(s.slug) ?? s.slug}</span>
      <div className="flex flex-wrap items-center gap-x-2">
        {s.required !== false ? (
          <Dots value={s.min_level ?? 2} onChange={(n) => setSkill(s.slug, { min_level: n })} label={nameOf.get(s.slug) ?? s.slug} />
        ) : null}
        <button type="button" onClick={() => setSkill(s.slug, s.required !== false ? { required: false, min_level: 1 } : { required: true, min_level: 2 })} className="h-9 rounded-lg px-2 text-xs font-semibold text-brand-fg hover:bg-tint-50">
          {s.required !== false ? "В желательные" : "В обязательные"}
        </button>
        <button type="button" aria-label={`Убрать ${nameOf.get(s.slug) ?? s.slug}`} onClick={() => setSkills((l) => l.filter((x) => x.slug !== s.slug))} className="h-9 w-9 rounded-lg text-muted hover:bg-tint-50">×</button>
      </div>
    </li>
  );

  if (!isNew && vq.isError) {
    return (
      <main className={PAGE.wide}>
        <ErrorNote>Вакансия не найдена.</ErrorNote>
        <Link to="/employer/vacancies" className="mt-3 inline-block text-sm font-semibold text-brand-fg hover:underline">← К вакансиям</Link>
      </main>
    );
  }
  if (!isNew && vq.isPending) return <Skeleton aria-hidden className="m-6 h-96 rounded-xl" />;

  return (
    <main className={PAGE.wide}>
      <Link to="/employer/vacancies" className="text-sm font-semibold text-brand-fg hover:underline">← К вакансиям</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-2xl font-semibold">{isNew ? "Новая вакансия" : "Вакансия"}</h1>
        <span className="rounded-md bg-tint-50 px-2 py-1 text-xs font-semibold text-brand-deep dark:text-brand-mid">{VACANCY_STATUS_LABEL[status] ?? status}</span>
      </div>
      {companyStatus && companyStatus !== "verified" && (
        <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          Компания ещё не проверена: черновики сохраняются, публикация станет доступна после проверки. <Link to="/employer/company" className="font-semibold underline">Компания</Link>
        </p>
      )}
      {company.isError && (
        <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          Сначала <Link to="/employer/company" className="font-semibold underline">зарегистрируйте компанию</Link>.
        </p>
      )}
      <p className="text-sm text-muted">Опишите требования на профессиональном языке: роль, грейд, навыки с минимальным уровнем. Система сама найдёт подходящие профили.</p>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <form onSubmit={onSave} noValidate className="flex min-w-0 flex-col gap-6 rounded-xl border border-hairline bg-card p-4 md:p-5">
        <fieldset className="flex flex-col gap-3" disabled={closed}>
          <legend className="mb-1 font-mono text-[17px] font-semibold">Роль и грейд</legend>
          <label className="flex flex-col gap-1 text-sm font-semibold">
            Название вакансии
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-invalid={touched && !!titleError} className={fieldClass} />
            {touched && titleError && <span className="text-xs font-normal text-error">{titleError}</span>}
          </label>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="flex flex-col gap-1 text-sm font-semibold">
              <span>Роль</span>
              <Select aria-label="Роль" disabled={closed} value={role} onChange={(v) => v && setRole(v)} options={Object.entries(ROLE_LABEL).map(([k, v]) => ({ value: k, label: v }))} className="font-normal" />
            </div>
            <div className="flex flex-col gap-1 text-sm font-semibold">
              <span>Грейд от</span>
              <Select aria-label="Грейд от" disabled={closed} value={gradeMin} onChange={(v) => v && setGradeMin(v)} options={GRADES.map((g) => ({ value: g, label: GRADE_LABEL[g] ?? g }))} className="font-normal" />
            </div>
            <div className="flex flex-col gap-1 text-sm font-semibold">
              <span>Грейд до</span>
              <Select aria-label="Грейд до" disabled={closed} value={gradeMax} onChange={(v) => v && setGradeMax(v)} options={GRADES.map((g) => ({ value: g, label: GRADE_LABEL[g] ?? g }))} className="font-normal" />
            </div>
          </div>
          {touched && gradeError && <p className="text-xs text-error">{gradeError}</p>}
        </fieldset>

        <fieldset className="flex min-w-0 flex-col gap-2" disabled={closed}>
          <legend className="font-mono text-[17px] font-semibold">Обязательные навыки</legend>
          <p className="text-xs text-muted">Минимальный уровень — точками. Каждая точка сужает выборку.</p>
          {required.length === 0 ? (
            <p className={cn("text-sm", noRequired ? "text-error" : "text-muted")}>Добавьте хотя бы один обязательный навык.</p>
          ) : (
            <ul className="flex flex-col gap-2">{required.map(SkillRow)}</ul>
          )}
        </fieldset>

        <fieldset className="flex min-w-0 flex-col gap-2" disabled={closed}>
          <legend className="font-mono text-[17px] font-semibold">Желательные навыки</legend>
          <p className="text-xs text-muted">Не отсекают кандидатов, но поднимают их в подборке.</p>
          {nice.length > 0 && <ul className="flex flex-col gap-2">{nice.map(SkillRow)}</ul>}
        </fieldset>

        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-sm font-semibold">
            Добавить навык
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Python, Kafka, Docker…" disabled={closed} className={fieldClass} />
          </label>
          {suggestions.length > 0 && (
            <ul aria-label="Подсказки навыков" className="flex flex-col gap-1">
              {suggestions.map((s) => (
                <li key={s.slug} className="flex items-center justify-between gap-2 rounded-lg border border-hairline px-3 py-1">
                  <span className="text-sm">{s.name}</span>
                  <span className="flex gap-1">
                    <Button size="sm" variant="outline" aria-label={`${s.name} в обязательные`} onClick={() => addSkill(s.slug, true)}>Обязательный</Button>
                    <Button size="sm" variant="ghost" aria-label={`${s.name} в желательные`} onClick={() => addSkill(s.slug, false)}>Желательный</Button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {query.trim() && suggestions.length === 0 && <p className="text-xs text-muted">Такого навыка нет в справочнике.</p>}
        </div>

        <fieldset className="flex flex-col gap-3" disabled={closed}>
          <legend className="mb-1 font-mono text-[17px] font-semibold">Формат и занятость</legend>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Формат работы">
            {Object.entries(FORMAT_LABEL).map(([k, v]) => <Chip key={k} active={formats.includes(k)} onClick={() => toggle(formats, setFormats, k)}>{v}</Chip>)}
          </div>
          {touched && formatError && <p className="text-xs text-error">{formatError}</p>}
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Занятость">
            {Object.entries(EMPLOYMENT_LABEL).map(([k, v]) => <Chip key={k} active={employment === k} onClick={() => setEmployment(k)}>{v}</Chip>)}
          </div>
          <label className="flex flex-col gap-1 text-sm font-semibold">
            Город
            <input value={city} onChange={(e) => setCity(e.target.value)} maxLength={100} className={fieldClass} />
          </label>
        </fieldset>

        <fieldset className="flex flex-col gap-1" disabled={closed}>
          <legend className="font-mono text-[17px] font-semibold">Зарплатная вилка *</legend>
          <p className="text-xs text-muted">В месяц, ₽, до вычета налогов. Без вилки вакансию сохранить нельзя.</p>
          <SalaryRangeInput
            value={{ from: from ? Number(from) : null, to: to ? Number(to) : null }}
            onChange={(v) => {
              setFrom(v.from == null ? "" : String(v.from));
              setTo(v.to == null ? "" : String(v.to));
            }}
            fromLabel="от"
            toLabel="до"
            disabled={closed}
            invalid={touched && !!salaryError}
          />
          {touched && salaryError && <p className="text-xs text-error">{salaryError}</p>}
          {(wide || loaded?.range_too_wide) && !salaryError && wide && (
            <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
              Слишком широкая вилка: верх больше низа более чем в 1,6 раза. Кандидат не поймёт, на что рассчитывать. Сохранить и опубликовать всё равно можно.
            </p>
          )}
        </fieldset>

        <fieldset className="flex min-w-0 flex-col gap-2" disabled={closed}>
          <legend className="font-mono text-[17px] font-semibold">Важные качества</legend>
          <p className="text-xs text-muted">Показываются словами и фактами, а не точками. Выбранные качества весят в подборе вдвое больше.</p>
          <div className="flex flex-col gap-2">
            {Object.keys(SIGNAL_LABEL).map((k) => (
              <label key={k} className="flex min-h-11 items-start gap-3 rounded-lg border border-hairline px-3 py-2 text-sm">
                <input type="checkbox" checked={qualities.includes(k)} onChange={() => toggle(qualities, setQualities, k, 4)} className="mt-1 h-4 w-4" />
                <span><span className="font-semibold">{SIGNAL_LABEL[k]}</span> <span className="text-muted">· {QUALITY_HINT[k]}</span></span>
              </label>
            ))}
          </div>
        </fieldset>

        <label className="flex flex-col gap-1 text-sm font-semibold">
          Описание
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={10000} rows={4} disabled={closed} className={cn(fieldClass, "h-auto py-2 font-normal")} />
        </label>

        {error != null && <ErrorNote>{vacancyErrorText(error)}</ErrorNote>}
        {note && !busy && <p role="status" className="rounded-lg bg-success-bg px-3 py-2 text-sm text-success">{note}</p>}
        {closed ? (
          <p className="text-sm text-muted">Вакансия закрыта и недоступна для правки.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {status !== "published" && <Button size="lg" disabled={busy} onClick={() => void onPublish()}>Опубликовать вакансию</Button>}
            <Button type="submit" size="lg" variant={status === "published" ? "primary" : "outline"} disabled={busy}>
              {busy ? "Сохраняем…" : status === "published" ? "Сохранить изменения" : "Сохранить черновик"}
            </Button>
            {status === "published" && <Button size="lg" variant="outline" disabled={busy} onClick={() => void onClose()}>Закрыть вакансию</Button>}
            {status === "published" && <Link to={`/employer/vacancies/${id}/shortlist`} className="inline-flex h-12 items-center rounded-lg px-5 font-semibold text-brand-fg hover:bg-tint-50">Подборка</Link>}
          </div>
        )}
      </form>
      <aside aria-label="Как читать" className="grid gap-3 rounded-xl border border-tint-200 bg-tint-50 p-4 text-13 lg:sticky lg:top-4">
        <p className="font-mono text-12 uppercase tracking-wide text-brand-fg">Как читать</p>
        <p>Каждая точка в обязательном навыке сужает выборку. Если кандидатов мало, снизьте уровень или переведите навык в желательные.</p>
        {strictest && (
          <p>
            Сейчас самое строгое требование: <b className="font-mono">{nameOf.get(strictest.slug) ?? strictest.slug} · {strictest.min_level} из 4</b>.
          </p>
        )}
        {loaded && status === "published" && (
          <Link to={`/employer/vacancies/${id}/shortlist`} className="inline-flex h-10 items-center justify-center rounded-lg bg-brand px-4 font-semibold text-on-brand hover:bg-brand-deep">
            Показать подборку
          </Link>
        )}
      </aside>
      </div>
    </main>
  );
}
