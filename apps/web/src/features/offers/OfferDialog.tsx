import { useQueryClient } from "@tanstack/react-query";
import { AcceptanceMeter, Button, Dialog, DialogContent, DialogDescription, DialogTitle, Sheet, SheetContent, SheetDescription, SheetTitle, formatRub, formatRubRange, type AcceptanceLevel } from "@fsp/ui";
import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateInterestInterestsPost, useCreateOfferOffersPost, useInviteFromInterestInterestsOfferIdInvitePost, useSalaryHintOffersSalaryHintPost } from "@/api/endpoints/offers/offers";
import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import { ContactMethod, type OfferForCompany } from "@/api/model";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { cn } from "@/shared/lib/cn";
import { canSendOffer, groupDigits, isWideRange, parseRub, rangeProblem } from "./offer-model";
import { invalidateOffers } from "./parts";
import { CONTACT_LABEL, EMP_INT_TEXT as IT, offerErrorText } from "./text";

const T = {
  title: (name: string) => `Приглашение кандидату ${name}`,
  lead: "Вилка обязательна: кандидат видит её первой. Контакты раскрываются только после «да».",
  vacancy: "Вакансия",
  noVacancy: "Без вакансии (прямое приглашение)",
  invitation: "Название приглашения",
  invitationHint: "Без вакансии название обязательно: кандидат увидит его в приглашении.",
  invDescription: "О чём приглашение",
  invContact: "Как связаться после принятия",
  range: "Зарплатная вилка в месяц, ₽ *",
  from: "от",
  to: "до",
  rangeHint: "Приглашение без вилки отправить нельзя: кандидат видит её первой.",
  missing: "Укажите обе границы вилки: приглашение без вилки отправить нельзя.",
  inverted: "Верхняя граница меньше нижней.",
  message: "Сообщение кандидату",
  placeholder: "Почему вы пишете именно ему: навыки, результаты, задачи.",
  info: "Срок ответа 7 дней. Приглашение придёт кандидату в Telegram и в кабинет. Контакты раскрываются только после принятия.",
  send: "Отправить приглашение",
  sending: "Отправляем…",
  cancel: "Отмена",
  live: "Живая подсказка",
  liveEmpty: "Укажите вилку: подсказка обновляется при вводе.",
  liveWait: "Считаем…",
  liveFail: "Подсказка недоступна, приглашение можно отправить.",
  median: "Медиана категории",
  expectations: "Ожидания кандидата",
  belowExpect: (v: string) => `Верх вилки ниже ожиданий кандидата (от ${v}). Скорее всего, ответ будет «нет».`,
  okExpect: (v: string) => `Вилка не ниже ожиданий кандидата (от ${v}).`,
  wide: "Слишком широкая вилка: разброс больше половины нижней границы. Кандидат не поймёт, на что рассчитывать.",
  advice: "Подсказки советуют, а не запрещают: вы решаете, сколько предложить.",
  already: "Этому кандидату уже отправлялись приглашения. Повторное приглашение по той же вакансии сервер не примет.",
  noPublished: "Нет опубликованных вакансий: можно отправить прямое приглашение.",
};

const LEVELS: string[] = ["low", "medium", "high"];

/** true на ширине ≥ query (в тестах без matchMedia — false: показываем Sheet). */
function useMedia(query: string): boolean {
  const get = () => typeof matchMedia === "function" && matchMedia(query).matches;
  const [v, setV] = useState(get);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(query);
    const on = () => setV(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return v;
}

export type OfferCandidate = { pseudoId: string; pseudonym: string; salaryMin: number | null };

/** offer — приглашение с вакансией; interest — первый шаг (E33-1); invite — приглашение по открытому интересу. */
export type DialogMode = "offer" | "interest" | "invite";

function Note({ tone, children }: { tone: "ok" | "warn"; children: ReactNode }) {
  return <p className={cn("rounded-lg px-3 py-2 text-sm", tone === "warn" ? "bg-warning-bg text-warning-fg" : "bg-success-bg text-success")}>{children}</p>;
}

function OfferForm({ candidate, vacancyId: initialVacancy, alreadyOffered, onClose, mode, interest }: { candidate: OfferCandidate; vacancyId: string; alreadyOffered: boolean; onClose: () => void; mode: DialogMode; interest?: OfferForCompany }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const vq = useListVacanciesVacanciesGet();
  const published = useMemo(() => (vq.data?.status === 200 ? vq.data.data : []).filter((v) => v.status === "published"), [vq.data]);
  const invite = mode === "invite";
  const isInterest = mode === "interest";
  const [vacancyId, setVacancyId] = useState(invite ? (interest?.vacancy?.id ?? "") : initialVacancy);
  const vacancy = published.find((v) => v.id === vacancyId);
  const [title, setTitle] = useState(invite ? (interest?.title ?? "") : "");
  const [description, setDescription] = useState("");
  const [contactMethod, setContactMethod] = useState<ContactMethod>(ContactMethod.platform);
  const [from, setFrom] = useState(invite && interest ? String(interest.salary_from) : "");
  const [to, setTo] = useState(invite && interest ? String(interest.salary_to) : "");
  const [message, setMessage] = useState("");
  const [touched, setTouched] = useState(false);
  // Один ключ на открытие модалки: повторный клик или ретрай не создаст второй приглашение.
  const key = useRef(crypto.randomUUID());

  // Вилка вакансии — отправная точка, пока человек ничего не вводил.
  useEffect(() => {
    if (vacancy && from === "" && to === "") {
      setFrom(String(vacancy.salary_from));
      setTo(String(vacancy.salary_to));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vacancy?.id]);

  const lo = parseRub(from);
  const hi = parseRub(to);
  const problem = rangeProblem(lo, hi);
  const wide = isWideRange(lo, hi);
  const canSend = isInterest ? problem === null : canSendOffer({ lo, hi, vacancyId, title });

  const hintM = useSalaryHintOffersSalaryHintPost();
  const hintMutate = hintM.mutate;
  useEffect(() => {
    if (problem) return;
    const t = setTimeout(() => hintMutate({ data: { vacancy_id: vacancyId || null, candidate_pseudo_id: candidate.pseudoId, salary_from: lo, salary_to: hi } }), 400);
    return () => clearTimeout(t);
  }, [vacancyId, candidate.pseudoId, lo, hi, problem, hintMutate]);
  const hint = !problem && hintM.data?.status === 200 ? hintM.data.data : null;

  const create = useCreateOfferOffersPost({
    request: { headers: { "Idempotency-Key": key.current } },
    mutation: {
      onSuccess: (r) => {
        void invalidateOffers(qc);
        onClose();
        nav(r.status === 201 ? `/employer/offers/${r.data.id}` : "/employer/offers");
      },
    },
  });

  const afterSave = (r: { data: unknown }) => {
    void invalidateOffers(qc);
    onClose();
    const id = (r.data as { id?: string } | null)?.id;
    nav(id ? `/employer/offers/${id}` : "/employer/offers");
  };
  const mark = useCreateInterestInterestsPost({ mutation: { onSuccess: afterSave } });
  const inviteM = useInviteFromInterestInterestsOfferIdInvitePost({ mutation: { onSuccess: afterSave } });
  const pending = create.isPending || mark.isPending || inviteM.isPending;
  const error = create.error ?? mark.error ?? inviteM.error;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!canSend || pending) return;
    if (isInterest) {
      mark.mutate({ data: { candidate_pseudo_id: candidate.pseudoId, vacancy_id: vacancyId || null, salary_from: lo, salary_to: hi, message: message.trim() || null } });
      return;
    }
    if (invite && interest) {
      inviteM.mutate({
        offerId: interest.id,
        data: {
          salary_from: lo,
          salary_to: hi,
          message: message.trim() || null,
          title: vacancyId ? null : title.trim(),
          description: vacancyId ? null : description.trim() || null,
          contact_method: vacancyId ? null : contactMethod,
        },
      });
      return;
    }
    create.mutate({
      data: {
        vacancy_id: vacancyId || null,
        title: vacancyId ? null : title.trim(),
        description: vacancyId ? null : description.trim() || null,
        contact_method: vacancyId ? null : contactMethod,
        candidate_pseudo_id: candidate.pseudoId,
        salary_from: lo,
        salary_to: hi,
        message: message.trim() || null,
      },
    });
  };

  const maxMessage = isInterest ? 300 : 2000;
  const rangeText = problem === "missing" ? T.missing : problem === "inverted" ? T.inverted : null;
  const expect = candidate.salaryMin;
  const level = hint && LEVELS.includes(hint.acceptance_hint) ? (hint.acceptance_hint as AcceptanceLevel) : null;

  return (
    <form onSubmit={submit} noValidate className="mt-4 grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="flex flex-col gap-4">
        {alreadyOffered && (
          <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
            {T.already}
          </p>
        )}
        {!invite && <label className="flex flex-col gap-1 text-sm font-semibold">
          {T.vacancy}
          <select
            value={vacancyId}
            onChange={(e) => {
              setVacancyId(e.target.value);
              setFrom("");
              setTo("");
            }}
            className={fieldClass}
          >
            <option value="">{T.noVacancy}</option>
            {published.map((v) => (
              <option key={v.id} value={v.id}>
                {v.title} · {v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}
              </option>
            ))}
          </select>
          {vq.isSuccess && published.length === 0 && <span className="text-xs font-normal text-muted">{T.noPublished}</span>}
        </label>}
        {!vacancyId && !isInterest && (
          <label className="flex flex-col gap-1 text-sm font-semibold">
            {T.invitation} *
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-invalid={touched && title.trim() === ""} className={fieldClass} />
            <span className={cn("text-xs font-normal", touched && title.trim() === "" ? "text-error" : "text-muted")}>{T.invitationHint}</span>
          </label>
        )}
        {!vacancyId && !isInterest && (
          <>
            <label className="flex flex-col gap-1 text-sm font-semibold">
              {T.invDescription}
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} rows={3} className={cn(fieldClass, "h-auto py-2 font-normal")} />
            </label>
            <label className="flex flex-col gap-1 text-sm font-semibold">
              {T.invContact}
              <select value={contactMethod} onChange={(e) => setContactMethod(e.target.value as ContactMethod)} className={fieldClass}>
                {Object.values(ContactMethod).map((m) => (
                  <option key={m} value={m}>{CONTACT_LABEL[m] ?? m}</option>
                ))}
              </select>
            </label>
          </>
        )}
        <fieldset className="flex flex-col gap-1">
          <legend className="text-sm font-semibold">{T.range}</legend>
          <div className="flex items-center gap-2">
            <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
              {T.from}
              <input inputMode="numeric" value={groupDigits(from)} onChange={(e) => setFrom(e.target.value.replace(/\D/g, ""))} aria-invalid={touched && !!problem} className={cn(fieldClass, "font-mono text-base")} />
            </label>
            <span aria-hidden className="pt-5 text-muted">
              –
            </span>
            <label className="flex flex-1 flex-col gap-1 text-xs text-muted">
              {T.to}
              <input inputMode="numeric" value={groupDigits(to)} onChange={(e) => setTo(e.target.value.replace(/\D/g, ""))} aria-invalid={touched && !!problem} className={cn(fieldClass, "font-mono text-base")} />
            </label>
          </div>
          <p role={touched && rangeText ? "alert" : undefined} className={cn("text-xs", touched && rangeText ? "text-error" : "text-muted")}>
            {touched && rangeText ? rangeText : T.rangeHint}
          </p>
        </fieldset>
        <label className="flex flex-col gap-1 text-sm font-semibold">
          {isInterest ? IT.messageInterest : T.message}
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={maxMessage} rows={isInterest ? 3 : 5} placeholder={T.placeholder} className={cn(fieldClass, "h-auto py-2 font-normal")} />
          <span className="self-end text-xs font-normal text-muted">{message.length} / {maxMessage}</span>
        </label>
        <p className="text-13 text-muted">{isInterest ? IT.infoInterest : invite ? IT.infoInvite : T.info}</p>
        {error && <ErrorNote>{offerErrorText(error)}</ErrorNote>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="lg" disabled={!canSend || pending}>
            {pending ? T.sending : isInterest ? IT.sendInterest : invite ? IT.sendInvite : T.send}
          </Button>
          <Button type="button" size="lg" variant="ghost" onClick={onClose}>
            {T.cancel}
          </Button>
        </div>
      </div>

      <aside aria-label={T.live} className="flex h-fit flex-col gap-3 rounded-xl border border-hairline bg-tint-50 p-4">
        <h3 className="font-mono text-17 font-semibold">{T.live}</h3>
        {lo !== null && hi !== null && !problem && <p className="font-mono text-16 font-bold">{formatRubRange(lo, hi)}</p>}
        {expect !== null && (
          <p className="text-13 text-muted">
            {T.expectations}: <b className="font-mono text-ink">от {formatRub(expect)}</b>
          </p>
        )}
        {problem ? (
          <p className="text-sm text-muted">{T.liveEmpty}</p>
        ) : (
          <>
            {(level && hint ? (
                <div className="flex flex-col gap-1">
                  <AcceptanceMeter level={level} />
                  <p className="text-12 text-muted">
                    Оценка по формуле, {Math.round(hint.p_accept * 100)}%.
                    {hint.category_median != null && (
                      <>
                        {" "}
                        {T.median}: <span className="font-mono">{formatRub(hint.category_median)}</span>.
                      </>
                    )}
                  </p>
                </div>
              ) : (
                <p role="status" className="text-sm text-muted">
                  {hintM.isError ? T.liveFail : T.liveWait}
                </p>
              ))}
            {hint?.suggested_salary_to != null && hint.suggested_p_accept != null && hi !== null && hint.suggested_salary_to > hi && (
              <div role="status" className="flex flex-col gap-2 rounded-lg bg-tint-100 px-3 py-2 text-sm">
                <p>{IT.suggest(formatRub(hint.suggested_salary_to), Math.round(hint.suggested_p_accept * 100))}</p>
                <Button type="button" size="sm" variant="outline" onClick={() => setTo(String(hint.suggested_salary_to))}>{IT.apply}</Button>
              </div>
            )}
            {hint?.avg_response_hours != null && <p className="text-12 text-muted">{IT.respHours(hint.avg_response_hours)}</p>}
            {expect !== null && hi !== null && (hi < expect ? <Note tone="warn">{T.belowExpect(formatRub(expect))}</Note> : <Note tone="ok">{T.okExpect(formatRub(expect))}</Note>)}
            {wide && <Note tone="warn">{T.wide}</Note>}
          </>
        )}
        <p className="text-12 text-muted">{T.advice}</p>
      </aside>
    </form>
  );
}

/**
 * Экран C: приглашение кандидату в модалке (≥ 1024 px — Dialog, на телефоне — полноэкранный Sheet).
 * Форма монтируется только при открытии: ключ идемпотентности и черновик свежие на каждое открытие.
 * `dark` — хозяин экрана тёмный (карточка кандидата): портал живёт вне его, тему задаём явно.
 */
export function OfferDialog({ open, onOpenChange, candidate, vacancyId = "", alreadyOffered = false, dark = false, mode = "offer", interest }: { open: boolean; onOpenChange: (v: boolean) => void; candidate: OfferCandidate; vacancyId?: string; alreadyOffered?: boolean; dark?: boolean; mode?: DialogMode; interest?: OfferForCompany }) {
  const desktop = useMedia("(min-width: 1024px)");
  const close = () => onOpenChange(false);
  const title = mode === "interest" ? IT.titleInterest(candidate.pseudonym) : mode === "invite" ? IT.titleInvite(candidate.pseudonym) : T.title(candidate.pseudonym);
  const lead = mode === "interest" ? IT.leadInterest : mode === "invite" ? IT.leadInvite : T.lead;
  const theme = dark ? "dark bg-card text-ink" : "";
  const form = <OfferForm candidate={candidate} vacancyId={vacancyId} alreadyOffered={alreadyOffered} onClose={close} mode={mode} interest={interest} />;
  if (desktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={cn("max-h-[90dvh] max-w-3xl overflow-y-auto", theme)}>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{lead}</DialogDescription>
          {form}
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className={cn("top-0 h-dvh max-h-none rounded-none border-t-0", theme)}>
        <SheetTitle>{title}</SheetTitle>
        <SheetDescription>{lead}</SheetDescription>
        {form}
      </SheetContent>
    </Sheet>
  );
}
