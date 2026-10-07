import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { useCreateOfferOffersPost, useSalaryHintOffersSalaryHintPost } from "@/api/endpoints/offers/offers";
import { useCandidateCardCandidatesPseudoIdCardGet } from "@/api/endpoints/search/search";
import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import type { SalaryHint } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL, rub } from "@/features/employer/text";
import { GRADE_LABEL, roleLabel } from "@/features/profile/text";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/button";
import { invalidateOffers } from "./parts";
import { ACCEPT_LABEL, offerErrorText } from "./text";

const num = (s: string) => (s.trim() === "" ? null : Math.max(0, Math.round(Number(s.replace(/\s/g, "")))) || null);

function Meter({ hint }: { hint: SalaryHint["acceptance_hint"] }) {
  const lvl = hint === "low" ? 1 : hint === "medium" ? 2 : 3;
  return (
    <div className="flex items-center gap-2" aria-label={`Вероятность принятия: ${ACCEPT_LABEL[hint as keyof typeof ACCEPT_LABEL] ?? hint}`}>
      {[1, 2, 3].map((i) => (
        <span key={i} className={cn("h-2 w-10 rounded-full", i <= lvl ? "bg-brand" : "bg-hairline")} />
      ))}
    </div>
  );
}

/** Приглашение кандидату (экран C): вилка обязательна, живая подсказка пересчитывается при вводе. */
export default function OfferComposer() {
  const [params] = useSearchParams();
  const pseudoId = params.get("candidate") ?? "";
  const nav = useNavigate();
  const qc = useQueryClient();
  const vq = useListVacanciesVacanciesGet();
  const published = useMemo(() => (vq.data?.status === 200 ? vq.data.data : []).filter((v) => v.status === "published"), [vq.data]);
  const [vacancyId, setVacancyId] = useState(params.get("vacancy") ?? "");
  const vacancy = published.find((v) => v.id === vacancyId);
  const cq = useCandidateCardCandidatesPseudoIdCardGet(pseudoId, { vacancy_id: vacancyId || undefined, source: "direct" }, { query: { enabled: !!pseudoId, retry: false } });
  const card = cq.data?.status === 200 ? cq.data.data : null;

  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [message, setMessage] = useState("");
  const [touched, setTouched] = useState(false);
  // Один ключ на открытие формы: повторный клик/ретрай не создаст второй приглашение.
  const key = useRef(crypto.randomUUID());

  // Подставляем вилку вакансии как отправную точку.
  useEffect(() => {
    if (vacancy && from === "" && to === "") {
      setFrom(String(vacancy.salary_from));
      setTo(String(vacancy.salary_to));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vacancy?.id]);

  const lo = num(from);
  const hi = num(to);
  const rangeError = lo === null || hi === null ? "Укажите обе границы вилки: приглашение без вилки отправить нельзя." : hi < lo ? "Верхняя граница не может быть меньше нижней." : null;

  const hintM = useSalaryHintOffersSalaryHintPost();
  const hintMutate = hintM.mutate;
  useEffect(() => {
    if (!vacancyId || !pseudoId || rangeError) return;
    const t = setTimeout(() => hintMutate({ data: { vacancy_id: vacancyId, candidate_pseudo_id: pseudoId, salary_from: lo, salary_to: hi } }), 400);
    return () => clearTimeout(t);
  }, [vacancyId, pseudoId, lo, hi, rangeError, hintMutate]);
  const hint = !rangeError && hintM.data?.status === 200 ? hintM.data.data : null;

  const create = useCreateOfferOffersPost({
    request: { headers: { "Idempotency-Key": key.current } },
    mutation: {
      onSuccess: (r) => {
        void invalidateOffers(qc);
        nav(r.status === 201 ? `/employer/offers/${r.data.id}` : "/employer/offers");
      },
    },
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (rangeError || !vacancyId || !pseudoId) return;
    create.mutate({ data: { vacancy_id: vacancyId, candidate_pseudo_id: pseudoId, salary_from: lo, salary_to: hi, message: message.trim() || null } });
  };

  if (!pseudoId) {
    return (
      <main className="mx-auto w-full max-w-3xl p-4 md:p-6">
        <ErrorNote>Не выбран кандидат. Откройте карточку кандидата и нажмите «Отправить приглашение».</ErrorNote>
      </main>
    );
  }
  const grade = card?.grade ? (GRADE_LABEL[card.grade] ?? card.grade) : null;
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 md:p-6">
      <Link to={`/employer/candidates/${pseudoId}${vacancyId ? `?vacancy=${vacancyId}` : ""}`} className="text-sm font-semibold text-brand-fg hover:underline">← К карточке кандидата</Link>
      <h1 className="font-mono text-2xl font-semibold">Приглашение кандидату {card?.pseudonym ?? ""}</h1>
      {card && (
        <p className="text-sm text-muted">
          {[grade, card.primary_role && roleLabel(card.primary_role), card.primary_stack.slice(0, 3).join(", "), card.salary_min ? `ожидания от ${rub(card.salary_min)}` : null].filter(Boolean).join(" · ")}
        </p>
      )}
      {cq.isError && <ErrorNote>Кандидат не найден или скрыл анкету.</ErrorNote>}
      {card && card.offers_from_you.length > 0 && (
        <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          Этому кандидату уже отправлялись приглашения. Повторное приглашение по той же вакансии сервер не примет.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-[1fr_320px]">
        <form onSubmit={submit} className="flex flex-col gap-4 rounded-xl border border-hairline bg-card p-4 md:p-5" noValidate>
          <label className="flex flex-col gap-1 text-sm font-semibold">
            Вакансия
            <select value={vacancyId} onChange={(e) => { setVacancyId(e.target.value); setFrom(""); setTo(""); }} className={fieldClass}>
              <option value="">Выберите вакансию</option>
              {published.map((v) => (
                <option key={v.id} value={v.id}>{v.title} · {v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}</option>
              ))}
            </select>
            {touched && !vacancyId && <span className="text-xs font-normal text-error">Выберите опубликованную вакансию.</span>}
            {vq.isSuccess && published.length === 0 && <span className="text-xs font-normal text-muted">Нет опубликованных вакансий.</span>}
          </label>
          <fieldset className="flex flex-col gap-1">
            <legend className="text-sm font-semibold">Зарплатная вилка в месяц, ₽ *</legend>
            <div className="flex items-center gap-2">
              <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
                от
                <input inputMode="numeric" value={from} onChange={(e) => setFrom(e.target.value)} aria-invalid={touched && !!rangeError} className={cn(fieldClass, "font-mono text-base text-ink")} />
              </label>
              <span aria-hidden className="pt-5 text-muted">–</span>
              <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
                до
                <input inputMode="numeric" value={to} onChange={(e) => setTo(e.target.value)} aria-invalid={touched && !!rangeError} className={cn(fieldClass, "font-mono text-base text-ink")} />
              </label>
            </div>
            <p className={cn("text-xs", touched && rangeError ? "text-error" : "text-muted")}>
              {touched && rangeError ? rangeError : "Приглашение без вилки отправить нельзя: кандидат видит её первой."}
            </p>
          </fieldset>
          <label className="flex flex-col gap-1 text-sm font-semibold">
            Сообщение кандидату
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={2000} rows={5} placeholder="Почему вы пишете именно ему: навыки, результаты, задачи." className={cn(fieldClass, "h-auto py-2 font-normal")} />
            <span className="self-end text-xs font-normal text-muted">{message.length} / 2000</span>
          </label>
          <p className="text-[13px] text-muted">
            Срок ответа 7 дней. Формат вакансии: {vacancy ? vacancy.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ") : "выберите вакансию"}. Приглашение придёт кандидату в Telegram и в кабинет. Контакты раскрываются только после принятия.
          </p>
          {create.isError && <ErrorNote>{offerErrorText(create.error)}</ErrorNote>}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="lg" disabled={create.isPending || !card}>{create.isPending ? "Отправляем…" : "Отправить приглашение"}</Button>
            <Link to={`/employer/candidates/${pseudoId}`} className="inline-flex h-12 items-center rounded-lg px-5 font-semibold hover:bg-tint-50">Отмена</Link>
          </div>
        </form>

        <aside aria-label="Живая подсказка" className="flex h-fit flex-col gap-3 rounded-xl border border-hairline bg-card p-4 md:p-5">
          <h2 className="font-mono text-[17px] font-semibold">Живая подсказка</h2>
          {!vacancyId || rangeError ? (
            <p className="text-sm text-muted">Выберите вакансию и укажите вилку: подсказка обновляется при вводе.</p>
          ) : !hint ? (
            <p role="status" className="text-sm text-muted">{hintM.isError ? "Подсказка недоступна, приглашение можно отправить." : "Считаем…"}</p>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <p className="text-sm font-semibold">Вероятность принятия: {ACCEPT_LABEL[hint.acceptance_hint as keyof typeof ACCEPT_LABEL] ?? hint.acceptance_hint}</p>
                <Meter hint={hint.acceptance_hint} />
                <p className="text-xs text-muted">Оценка по формуле: вилка против ожиданий, формат, стек, рейтинг компании. {Math.round(hint.p_accept * 100)}%</p>
              </div>
              {hint.candidate_min != null && (
                <p className={cn("rounded-lg px-3 py-2 text-sm", hint.below_candidate_min ? "bg-warning-bg text-warning-fg" : "bg-success-bg text-success")}>
                  {hint.below_candidate_min ? `Верх вилки ниже ожиданий кандидата (от ${rub(hint.candidate_min)}). Скорее всего, ответ будет «нет».` : `Вилка не ниже ожиданий кандидата (от ${rub(hint.candidate_min)}).`}
                </p>
              )}
              {hint.range_too_wide && <p className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">Слишком широкая вилка: верх больше низа более чем в 1,6 раза. Кандидат не поймёт, на что рассчитывать.</p>}
            </>
          )}
          <p className="text-xs text-muted">Подсказки советуют, а не запрещают: вы решаете, сколько предложить.</p>
        </aside>
      </div>
    </main>
  );
}
