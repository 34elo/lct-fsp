import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { useGetTaxonomyTaxonomyGet } from "@/api/endpoints/taxonomy/taxonomy";
import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import { useSearchCandidatesSearchCandidatesPost } from "@/api/endpoints/search/search";
import type { CandidateCard, SearchFilters, SearchRequestSort } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { GRADE_LABEL, ROLE_LABEL } from "@/features/profile/text";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/button";
import { CandidateTile } from "./CandidateTile";
import { FORMAT_LABEL, SORT_LABEL } from "./text";

const GRADES = Object.keys(GRADE_LABEL);
const sel = cn(fieldClass, "appearance-none");

interface Form {
  role: string;
  gradeMin: string;
  gradeMax: string;
  format: string;
  skills: string[];
  fspOnly: boolean;
  activeOnly: boolean;
  sort: SearchRequestSort;
}
const EMPTY: Form = { role: "", gradeMin: "", gradeMax: "", format: "", skills: [], fspOnly: false, activeOnly: false, sort: "match" };

function toFilters(f: Form): SearchFilters {
  const out: SearchFilters = {};
  if (f.role) out.roles = [f.role as never];
  if (f.gradeMin) out.grade_min = f.gradeMin as never;
  if (f.gradeMax) out.grade_max = f.gradeMax as never;
  if (f.format) out.formats = [f.format as never];
  if (f.skills.length) out.skills_must = f.skills.map((slug) => ({ slug }));
  if (f.fspOnly) out.fsp_only = true;
  if (f.activeOnly) out.active_only = true;
  return out;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-[13px] font-medium text-muted">
      {label}
      {children}
    </label>
  );
}

/**
 * Выдача поиска (экраны A/E2/E4). С `vacancy` — подборка под вакансию: сортировка по совпадению,
 * match-ring и объяснение по путям графа. Фильтры пересобирают выдачу, «Показать ещё» — курсор.
 */
export default function Search() {
  const { id: pathVacancy } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const vacancyId = pathVacancy ?? params.get("vacancy");

  const vacancies = useListVacanciesVacanciesGet();
  const taxonomy = useGetTaxonomyTaxonomyGet();
  const search = useSearchCandidatesSearchCandidatesPost();

  const [form, setForm] = useState<Form>(EMPTY);
  const [items, setItems] = useState<CandidateCard[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const session = useRef<string | null>(null);
  const seq = useRef(0);

  const myVacancies = useMemo(() => (vacancies.data?.status === 200 ? vacancies.data.data : []), [vacancies.data]);
  const vacancy = myVacancies.find((v) => v.id === vacancyId) ?? null;
  // Ответ /taxonomy в схеме без модели (unknown): сужаем до нужных полей.
  const taxSkills = useMemo(() => ((taxonomy.data?.data as { skills?: { slug: string; name: string }[] } | undefined)?.skills ?? []), [taxonomy.data]);
  const skillName = useMemo(() => new Map(taxSkills.map((s) => [s.slug, s.name])), [taxSkills]);

  // При выборе вакансии подставляем её роль и грейды как стартовые фильтры.
  useEffect(() => {
    if (vacancy) setForm((f) => ({ ...f, role: vacancy.role, gradeMin: vacancy.grade_min, gradeMax: vacancy.grade_max, sort: "match" }));
  }, [vacancy?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = useCallback(
    (next: string | null) => {
      const n = ++seq.current;
      setFailed(false);
      search.mutate(
        {
          data: {
            filters: toFilters(form),
            sort: form.sort,
            cursor: next,
            limit: 20,
            vacancy_id: vacancyId,
            session_id: next ? session.current : null,
          },
        },
        {
          onSuccess: (r) => {
            if (n !== seq.current || r.status !== 200) return;
            session.current = r.data.session_id;
            setItems((old) => (next ? [...old, ...r.data.items] : r.data.items));
            setCursor(r.data.next_cursor);
            setTotal(r.data.total);
          },
          onError: () => n === seq.current && setFailed(true),
        },
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [form, vacancyId],
  );

  // Ждём список вакансий, чтобы подборка не стартовала без стартовых фильтров вакансии.
  const ready = !vacancyId || vacancy !== null || vacancies.isError;
  const formKey = JSON.stringify(form);
  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(() => run(null), 150);
    return () => clearTimeout(t);
  }, [formKey, vacancyId, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const pickVacancy = (id: string) => {
    if (pathVacancy) navigate(id ? `/employer/vacancies/${id}/shortlist` : "/employer/search");
    else setParams(id ? { vacancy: id } : {});
    if (!id) setForm(EMPTY);
  };
  const addSkill = (slug: string) => slug && !form.skills.includes(slug) && set("skills", [...form.skills, slug]);

  const pending = search.isPending;
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 md:p-6">
      <h1 className="font-mono text-2xl font-semibold">{vacancy ? `Подборка: ${vacancy.title}` : "Поиск кандидатов"}</h1>
      <p className="text-sm text-muted">Карточки анонимны: имя, контакты и компании открываются после принятия оффера.</p>

      <section aria-label="Фильтры" className="grid grid-cols-2 gap-3 rounded-xl border border-hairline bg-card p-4 md:grid-cols-4">
        <div className="col-span-2 md:col-span-4">
          <Field label="Вакансия (подборка)">
            <select className={sel} value={vacancyId ?? ""} onChange={(e) => pickVacancy(e.target.value)} aria-label="Вакансия">
              <option value="">Без вакансии: свободный поиск</option>
              {myVacancies.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.title}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Роль">
          <select className={sel} value={form.role} onChange={(e) => set("role", e.target.value)} aria-label="Роль">
            <option value="">Любая</option>
            {Object.entries(ROLE_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Формат">
          <select className={sel} value={form.format} onChange={(e) => set("format", e.target.value)} aria-label="Формат">
            <option value="">Любой</option>
            {Object.entries(FORMAT_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Грейд от">
          <select className={sel} value={form.gradeMin} onChange={(e) => set("gradeMin", e.target.value)} aria-label="Грейд от">
            <option value="">Любой</option>
            {GRADES.map((g) => (
              <option key={g} value={g}>{GRADE_LABEL[g]}</option>
            ))}
          </select>
        </Field>
        <Field label="Грейд до">
          <select className={sel} value={form.gradeMax} onChange={(e) => set("gradeMax", e.target.value)} aria-label="Грейд до">
            <option value="">Любой</option>
            {GRADES.map((g) => (
              <option key={g} value={g}>{GRADE_LABEL[g]}</option>
            ))}
          </select>
        </Field>
        <div className="col-span-2 md:col-span-4">
          <Field label="Обязательные навыки">
            <select className={sel} value="" onChange={(e) => addSkill(e.target.value)} aria-label="Добавить навык">
              <option value="">Добавить навык…</option>
              {taxSkills.map((s) => (
                <option key={s.slug} value={s.slug}>{s.name}</option>
              ))}
            </select>
          </Field>
          {form.skills.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {form.skills.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => set("skills", form.skills.filter((x) => x !== s))}
                  aria-label={`Убрать навык ${skillName.get(s) ?? s}`}
                  className="inline-flex h-[30px] items-center gap-1.5 rounded-md border border-tint-200 bg-tint-50 px-[11px] font-mono text-[12.5px] text-brand-deep dark:text-brand-mid"
                >
                  {skillName.get(s) ?? s} <span aria-hidden>×</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.fspOnly} onChange={(e) => set("fspOnly", e.target.checked)} className="size-4 accent-[var(--brand)]" />
          Только с достижениями ФСП
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.activeOnly} onChange={(e) => set("activeOnly", e.target.checked)} className="size-4 accent-[var(--brand)]" />
          Только активно ищут
        </label>
        <div className="col-span-2 flex items-end justify-between gap-3 md:col-span-2">
          <Field label="Сортировка">
            <select className={sel} value={form.sort ?? undefined} onChange={(e) => set("sort", e.target.value as SearchRequestSort)} aria-label="Сортировка">
              {Object.entries(SORT_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </Field>
          <Button variant="ghost" size="sm" onClick={() => setForm(vacancy ? { ...EMPTY, role: vacancy.role, gradeMin: vacancy.grade_min, gradeMax: vacancy.grade_max } : EMPTY)}>
            Сбросить
          </Button>
        </div>
      </section>

      {failed && <ErrorNote>Не удалось загрузить выдачу. Попробуйте ещё раз.</ErrorNote>}

      <p role="status" className="text-sm text-muted">
        {pending && items.length === 0 ? "Ищем…" : total !== null ? `Найдено: ${total}` : ""}
      </p>

      {total === 0 && !pending && (
        <p className="rounded-xl border border-hairline bg-card p-5 text-sm">Никого не нашли: ослабьте фильтры или уберите обязательные навыки.</p>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {items.map((c) => (
          <CandidateTile key={c.pseudo_id} card={c} vacancyId={vacancyId} />
        ))}
      </div>

      {cursor && (
        <Button variant="outline" onClick={() => run(cursor)} disabled={pending} className="self-center">
          {pending ? "Загружаем…" : "Показать ещё"}
        </Button>
      )}
    </main>
  );
}
