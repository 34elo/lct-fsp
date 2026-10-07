import { useEffect, useState, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { getGetMyCompanyCompaniesMeGetQueryKey, useGetMyCompanyCompaniesMeGet, usePatchMyCompanyCompaniesMePatch, useRegisterCompanyCompaniesPost } from "@/api/endpoints/companies/companies";
import { ApiError } from "@/api/mutator";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/button";
import { COMPANY_STATUS_HINT, COMPANY_STATUS_LABEL, vacancyErrorText } from "./text";

/** Компания работодателя: регистрация, правка, статус модерации. */
export default function Company() {
  const qc = useQueryClient();
  const q = useGetMyCompanyCompaniesMeGet({ query: { retry: false } });
  const company = q.data?.status === 200 ? q.data.data : null;
  const missing = q.error instanceof ApiError && q.error.status === 404;

  const [name, setName] = useState("");
  const [inn, setInn] = useState("");
  const [site, setSite] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (company) {
      setName(company.name);
      setInn(company.inn ?? "");
      setSite(company.site ?? "");
      setDescription(company.description ?? "");
    }
  }, [company?.id, company?.name]); // eslint-disable-line react-hooks/exhaustive-deps

  const done = () => {
    setSaved(true);
    void qc.invalidateQueries({ queryKey: getGetMyCompanyCompaniesMeGetQueryKey() });
  };
  const register = useRegisterCompanyCompaniesPost({ mutation: { onSuccess: done } });
  const patch = usePatchMyCompanyCompaniesMePatch({ mutation: { onSuccess: done } });
  const m = company ? patch : register;

  const nameError = name.trim().length < 2 ? "Укажите название компании." : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setSaved(false);
    if (nameError) return;
    const data = { name: name.trim(), inn: inn.trim() || null, site: site.trim() || null, description: description.trim() || null };
    if (company) patch.mutate({ data });
    else register.mutate({ data });
  };

  const status = company?.status ?? "pending";
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-4 p-4 md:p-6">
      <h1 className="font-mono text-2xl font-semibold">Компания</h1>
      {q.isPending && <p role="status" className="text-muted">Загрузка…</p>}
      {q.isError && !missing && <ErrorNote>Не удалось загрузить компанию.</ErrorNote>}
      {missing && <p className="rounded-xl border border-hairline bg-card p-4 text-sm">Компания ещё не зарегистрирована. Заполните данные: после проверки администратором ФСП откроются публикация вакансий и приглашения.</p>}
      {company && (
        <section aria-label="Статус" className="flex flex-col gap-1 rounded-xl border border-hairline bg-card p-4">
          <p className="text-sm font-semibold">
            Статус:{" "}
            <span className={cn("rounded-md px-2 py-1 text-xs", status === "verified" ? "bg-success-bg text-success" : status === "pending" ? "bg-warning-bg text-warning-fg" : "bg-error-bg text-error")}>
              {COMPANY_STATUS_LABEL[status] ?? status}
            </span>
          </p>
          <p className="text-sm text-muted">{COMPANY_STATUS_HINT[status] ?? ""}</p>
        </section>
      )}
      {(company || missing) && (
        <form onSubmit={submit} noValidate className="flex flex-col gap-4 rounded-xl border border-hairline bg-card p-4 md:p-5">
          <label className="flex flex-col gap-1 text-sm font-semibold">
            Название *
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={200} aria-invalid={touched && !!nameError} className={fieldClass} />
            {touched && nameError && <span className="text-xs font-normal text-error">{nameError}</span>}
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm font-semibold">
              ИНН
              <input inputMode="numeric" value={inn} onChange={(e) => setInn(e.target.value)} maxLength={12} className={cn(fieldClass, "font-mono")} />
            </label>
            <label className="flex flex-col gap-1 text-sm font-semibold">
              Сайт
              <input value={site} onChange={(e) => setSite(e.target.value)} maxLength={200} placeholder="https://" className={fieldClass} />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm font-semibold">
            О компании
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={5000} rows={5} className={cn(fieldClass, "h-auto py-2 font-normal")} />
          </label>
          {m.isError && <ErrorNote>{vacancyErrorText(m.error)}</ErrorNote>}
          {saved && !m.isPending && <p role="status" className="rounded-lg bg-success-bg px-3 py-2 text-sm text-success">Сохранено.</p>}
          <Button type="submit" size="lg" className="self-start" disabled={m.isPending}>
            {m.isPending ? "Сохраняем…" : company ? "Сохранить" : "Зарегистрировать компанию"}
          </Button>
        </form>
      )}
    </main>
  );
}
