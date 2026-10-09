import { useState, type FormEvent } from "react";

import { Button, Card, Field, FieldInput, Panel, QueryBar } from "@fsp/ui";

import { useRegisterCompanyCompaniesPost } from "@/api/endpoints/companies/companies";
import { useCreateNeedNeedsPost } from "@/api/endpoints/needs/needs";
import { ApiError } from "@/api/mutator";
import { FlowSteps } from "@/features/assessment/ui";
import { needChips } from "@/features/needs/NeedCategories";
import { Gloss } from "@/shared/Gloss";
import { useAuth } from "@/shared/lib/auth";
import { PAGE } from "@/shared/lib/page";
import { saveLastNeed } from "./match-model";
import { criteriaKey, fromFilters } from "./query-model";
import { MATCH_TEXT as M, ONBOARDING_TEXT as T } from "./text";

const INN_RE = /^(\d{10}|\d{12})$/;

/**
 * Онбординг новой компании (E39-7): 1. данные компании → 2. первый запрос «кого ищете» → 3. как устроен подбор.
 * Пропустить можно на любом шаге: `onSkip` закрывает всё, дальше экран подбора честно показывает пустые состояния.
 * `onDone(needId)` — на последнем шаге; `needId` есть, если запрос был создан.
 */
export function EmployerOnboarding({ onSkip, onDone }: { onSkip: () => void; onDone: (needId: string | null) => void }) {
  const { me, reloadMe } = useAuth();
  // Компания уже есть (вернулись из пропуска) — начинаем со второго шага.
  const [step, setStep] = useState(me?.company ? 2 : 1);
  const [needId, setNeedId] = useState<string | null>(null);

  return (
    <div className={`${PAGE.narrow} gap-6`} data-testid="employer-onboarding">
      <header className="flex flex-col gap-1">
        <h1 className="text-24 font-bold">{T.title}</h1>
      </header>
      <FlowSteps current={step} steps={T.steps} label={T.stepsLabel} />
      {step === 1 && <CompanyStep onSaved={() => reloadMe().then(() => setStep(2))} />}
      {step === 2 && (
        <NeedStep
          companyId={me?.company?.id}
          onNext={(id) => {
            setNeedId(id);
            setStep(3);
          }}
        />
      )}
      {step === 3 && <HowStep onDone={() => onDone(needId)} />}
      <button type="button" onClick={onSkip} data-testid="onboarding-skip" className="inline-flex min-h-11 items-center self-start text-14 font-semibold text-muted hover:text-ink hover:underline">
        {step === 1 ? T.skipAll : T.skip}
      </button>
    </div>
  );
}

function CompanyStep({ onSaved }: { onSaved: () => Promise<void> }) {
  const t = T.company;
  const [name, setName] = useState("");
  const [site, setSite] = useState("");
  const [inn, setInn] = useState("");
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const register = useRegisterCompanyCompaniesPost();

  const nameError = name.trim().length < 2 ? t.nameError : undefined;
  const innError = inn.trim() && !INN_RE.test(inn.trim()) ? t.innError : undefined;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (nameError || innError) return;
    setBusy(true);
    setError(null);
    try {
      await register.mutateAsync({ data: { name: name.trim(), inn: inn.trim() || null, site: site.trim() || null } });
    } catch (err) {
      // Компания уже создана (повторный клик, вторая вкладка) — идём дальше.
      if (!(err instanceof ApiError && err.code === "company_exists")) {
        setError(t.failed);
        setBusy(false);
        return;
      }
    }
    await onSaved();
  };

  return (
    <Card className="flex flex-col gap-4 p-5 md:p-6">
      <header className="flex flex-col gap-1">
        <h2 className="text-20 font-semibold">{t.title}</h2>
        <p className="text-14 text-muted">{t.lead}</p>
      </header>
      <form onSubmit={submit} noValidate className="flex flex-col gap-3" data-testid="onboarding-company-form">
        <Field label={t.name} error={touched ? nameError : undefined}>
          <FieldInput value={name} onChange={(e) => setName(e.target.value)} maxLength={200} autoComplete="organization" data-testid="onboarding-company-name" />
        </Field>
        <Field label={t.site}>
          <FieldInput value={site} onChange={(e) => setSite(e.target.value)} maxLength={300} placeholder={t.sitePlaceholder} inputMode="url" data-testid="onboarding-company-site" />
        </Field>
        <Field label={t.inn} hint={t.innHint} error={touched ? innError : undefined}>
          <FieldInput value={inn} onChange={(e) => setInn(e.target.value)} maxLength={12} inputMode="numeric" data-testid="onboarding-company-inn" />
        </Field>
        {error && (
          <p role="alert" className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" loading={busy} data-testid="onboarding-company-submit">
          {busy ? t.busy : t.submit}
        </Button>
      </form>
    </Card>
  );
}

function NeedStep({ companyId, onNext }: { companyId?: string; onNext: (needId: string | null) => void }) {
  const t = T.need;
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const create = useCreateNeedNeedsPost();

  const submit = (value: string) => {
    setError(null);
    create.mutate(
      { data: { text: value } },
      {
        onSuccess: (r) => {
          if (r.status !== 201) return;
          saveLastNeed({ id: r.data.id, text: value, chips: needChips(r.data), company: companyId, qs: criteriaKey(fromFilters(r.data.filters)) });
          onNext(r.data.id);
        },
        onError: (err) => setError(err instanceof ApiError && err.code === "need_empty" ? M.notUnderstood : M.failed),
      },
    );
  };

  return (
    <Card className="flex flex-col gap-4 p-5 md:p-6" data-testid="onboarding-need">
      <header className="flex flex-col gap-1">
        <h2 className="text-20 font-semibold">{t.title}</h2>
        <p className="text-14 text-muted">{t.lead}</p>
      </header>
      <QueryBar value={text} onChange={setText} onSubmit={submit} loading={create.isPending} placeholder={M.placeholder} label={M.queryLabel} submitLabel={M.submit} />
      {error && (
        <p role="alert" className="rounded-lg bg-error-bg px-3 py-2 text-14 text-error">
          {error}
        </p>
      )}
      <ul aria-label={M.examples} className="m-0 flex list-none flex-col gap-2 p-0">
        {M.exampleList.map((x) => (
          <li key={x}>
            <button
              type="button"
              disabled={create.isPending}
              onClick={() => {
                setText(x);
                submit(x);
              }}
              className="min-h-11 w-full rounded-lg border border-hairline px-3 py-2.5 text-left text-14 hover:border-brand hover:bg-tint-50 disabled:opacity-60"
            >
              {x}
            </button>
          </li>
        ))}
      </ul>
      <Button variant="outline" className="self-start" onClick={() => onNext(null)} data-testid="onboarding-need-later">
        {t.skip}
      </Button>
    </Card>
  );
}

function HowStep({ onDone }: { onDone: () => void }) {
  const t = T.how;
  return (
    <div className="flex flex-col gap-4" data-testid="onboarding-how">
      <header className="flex flex-col gap-1">
        <h2 className="text-20 font-semibold">{t.title}</h2>
        <p className="text-14 text-muted">{t.lead}</p>
      </header>
      <ul className="m-0 grid list-none gap-3 p-0 md:grid-cols-3">
        {t.cards.map((c) => (
          <li key={c.key}>
            <Panel className="flex h-full flex-col gap-2" data-testid={`onboarding-card-${c.key}`}>
              <b className="font-mono text-16 font-semibold">
                <Gloss k={c.key}>{c.title}</Gloss>
              </b>
              <p className="text-14 text-muted">{c.text}</p>
            </Panel>
          </li>
        ))}
      </ul>
      <Button size="lg" className="self-start" onClick={onDone} data-testid="onboarding-done">
        {t.done}
      </Button>
    </div>
  );
}
