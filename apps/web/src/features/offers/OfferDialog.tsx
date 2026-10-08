import { useQueryClient } from "@tanstack/react-query";
import { type AcceptanceLevel, AcceptanceMeter, Button, cn, Dialog, DialogContent, DialogDescription, DialogTitle, formatRub, Lbl, Num, SalaryRangeInput, SegmentedControl, Select, Sheet, SheetContent, SheetDescription, SheetTitle, Skeleton } from "@fsp/ui";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useListTasksEmployerTasksGet } from "@/api/endpoints/assessment/assessment";
import { useCreateInterestInterestsPost, useCreateOfferOffersPost, useInviteFromInterestInterestsOfferIdInvitePost, useSalaryHintOffersSalaryHintPost } from "@/api/endpoints/offers/offers";
import { useListVacanciesVacanciesGet } from "@/api/endpoints/vacancies/vacancies";
import { ContactMethod, SalaryBasis, type OfferForCompany } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { fieldClass } from "@/features/auth/ui";
import { FORMAT_LABEL } from "@/features/employer/text";
import { displayPseudonym } from "@/shared/lib/pseudonym";
import { canSendOffer, isWideRange, parseRub, rangeProblem } from "./offer-model";
import { invalidateOffers } from "./parts";
import { CONTACT_LABEL, EMP_INT_TEXT as IT, offerErrorText } from "./text";

const T = {
  title: (name: string) => `Приглашение · ${name}`,
  lead: "Вилка обязательна: кандидат видит её первой. Контакты раскрываются только после «да».",
  vacancy: "Вакансия",
  noVacancy: "Без вакансии (прямое приглашение)",
  invitation: "Название приглашения",
  invitationHint: "Без вакансии название обязательно: кандидат увидит его в приглашении.",
  invDescription: "О чём приглашение",
  invContact: "Как связаться после принятия",
  range: "Вилка в месяц, ₽",
  from: "от",
  to: "до",
  basisLabel: "База вилки",
  gross: "до НДФЛ",
  net: "на руки",
  rangeHint: "Приглашение без вилки отправить нельзя: кандидат видит её первой.",
  missing: "Укажите обе границы вилки: приглашение без вилки отправить нельзя.",
  inverted: "Верхняя граница меньше нижней.",
  wideShort: "Вилка шире допустимой",
  message: "Сообщение",
  placeholder: "Почему вы пишете именно ему: навыки, результаты, задачи.",
  task: "Задание · по желанию",
  noTask: "Без задания",
  tasksFail: "Список заданий недоступен: приглашение можно отправить без задания.",
  info: "Срок ответа 7 дней. Приглашение придёт кандидату в Telegram и в кабинет. Контакты раскрываются только после принятия.",
  send: "Отправить",
  retry: "Повторить",
  sending: "Отправляем…",
  close: "Закрыть",
  sentOffer: "Приглашение отправлено",
  cancel: "Отмена",
  live: "Прогноз ответа",
  liveEmpty: "Укажите вилку — прогноз появится здесь",
  liveWait: "Считаем…",
  liveFail: "Прогноз недоступен, приглашение можно отправить.",
  raise: "поднимите верх до",
  failed: (s: number | null) => `Не отправилось${s ? ` · ошибка ${s}` : ""}`,
  median: "Медиана категории",
  belowExpect: (v: string) => `Верх вилки ниже ожиданий кандидата (от ${v}). Скорее всего, ответ будет «нет».`,
  okExpect: (v: string) => `Вилка не ниже ожиданий кандидата (от ${v}).`,
  wide: "Слишком широкая вилка: разброс больше половины нижней границы. Кандидат не поймёт, на что рассчитывать.",
  advice: "Подсказки советуют, а не запрещают: вы решаете, сколько предложить.",
  already: "Этому кандидату уже отправлялись приглашения. Повторное приглашение по той же вакансии сервер не примет.",
  noPublished: "Нет опубликованных вакансий: можно отправить прямое приглашение.",
};

const LEVELS: string[] = ["low", "medium", "high"];

/** 240 000 → «240 тыс.», иначе полная сумма. */
function formatTh(v: number): string {
  return v % 1000 === 0 ? `${v / 1000} тыс.` : formatRub(v);
}

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

function OfferForm({ candidate, vacancyId: initialVacancy, alreadyOffered, onClose, mode, interest, stay }: { candidate: OfferCandidate; vacancyId: string; alreadyOffered: boolean; onClose: () => void; mode: DialogMode; interest?: OfferForCompany; stay: boolean }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const vq = useListVacanciesVacanciesGet();
  const published = useMemo(() => (vq.data?.status === 200 ? vq.data.data : []).filter((v) => v.status === "published"), [vq.data]);
  const invite = mode === "invite";
  const isInterest = mode === "interest";
  const tq = useListTasksEmployerTasksGet({ query: { enabled: !isInterest, retry: false } });
  const tasks = useMemo(() => {
    const seen = new Set<string>();
    return (tq.data?.status === 200 ? tq.data.data : []).filter((t) => (seen.has(t.family_id) ? false : (seen.add(t.family_id), true)));
  }, [tq.data]);
  const [vacancyId, setVacancyId] = useState(invite ? (interest?.vacancy?.id ?? "") : initialVacancy);
  const vacancy = published.find((v) => v.id === vacancyId);
  const [title, setTitle] = useState(invite ? (interest?.title ?? "") : "");
  const [description, setDescription] = useState("");
  const [contactMethod, setContactMethod] = useState<ContactMethod>(ContactMethod.platform);
  const [from, setFrom] = useState(invite && interest ? String(interest.salary_from) : "");
  const [to, setTo] = useState(invite && interest ? String(interest.salary_to) : "");
  const [basis, setBasis] = useState<SalaryBasis>(SalaryBasis.gross);
  const [message, setMessage] = useState("");
  const [familyId, setFamilyId] = useState("");
  const [touched, setTouched] = useState(false);
  const [sent, setSent] = useState(false);
  // Один ключ на открытие модалки: повторный клик или ретрай не создаст второе приглашение.
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

  const afterSave = (r: { data: unknown }) => {
    void invalidateOffers(qc);
    if (stay) {
      setSent(true);
      return;
    }
    onClose();
    const id = (r.data as { id?: string } | null)?.id;
    nav(id ? `/employer/offers/${id}` : "/employer/offers");
  };
  const create = useCreateOfferOffersPost({ request: { headers: { "Idempotency-Key": key.current } }, mutation: { onSuccess: afterSave } });
  const mark = useCreateInterestInterestsPost({ mutation: { onSuccess: afterSave } });
  const inviteM = useInviteFromInterestInterestsOfferIdInvitePost({ mutation: { onSuccess: afterSave } });
  const pending = create.isPending || mark.isPending || inviteM.isPending;
  const error = create.error ?? mark.error ?? inviteM.error;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (!canSend || pending) return;
    const msg = message.trim() || null;
    const task = familyId ? { family_id: familyId } : null;
    if (isInterest) {
      mark.mutate({ data: { candidate_pseudo_id: candidate.pseudoId, vacancy_id: vacancyId || null, salary_from: lo, salary_to: hi, salary_basis: basis, message: msg } });
      return;
    }
    if (invite && interest) {
      inviteM.mutate({
        offerId: interest.id,
        data: {
          salary_from: lo,
          salary_to: hi,
          message: msg,
          title: vacancyId ? null : title.trim(),
          description: vacancyId ? null : description.trim() || null,
          contact_method: vacancyId ? null : contactMethod,
          task,
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
        salary_basis: basis,
        message: msg,
        task,
      },
    });
  };

  if (sent) {
    return (
      <div role="status" className="mt-4 flex flex-col gap-4">
        <p className="rounded-lg bg-success-bg px-3 py-3 text-sm font-semibold text-success">{isInterest ? IT.interestSent : T.sentOffer}</p>
        <div>
          <Button type="button" size="lg" onClick={onClose}>
            {T.close}
          </Button>
        </div>
      </div>
    );
  }

  const maxMessage = isInterest ? 300 : 2000;
  const rangeText = problem === "missing" ? T.missing : problem === "inverted" ? T.inverted : null;
  const rangeBad = touched && !!rangeText;
  const expect = candidate.salaryMin;
  const level = hint && LEVELS.includes(hint.acceptance_hint) ? (hint.acceptance_hint as AcceptanceLevel) : null;
  const upper = hint?.suggested_salary_to != null && hint.suggested_p_accept != null && hi !== null && hint.suggested_salary_to > hi ? hint : null;
  const sendLabel = error ? T.retry : pending ? T.sending : T.send;
  const inputBad = rangeBad || (wide && !problem);

  return (
    <form onSubmit={submit} noValidate className="mt-4 flex flex-col gap-4">
      {alreadyOffered && (
        <p role="status" className="rounded-lg bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          {T.already}
        </p>
      )}
      {!invite && (
        <div className="flex flex-col gap-1">
          <Lbl>{T.vacancy}</Lbl>
          <Select
            aria-label={T.vacancy}
            value={vacancyId}
            onChange={(v) => {
              setVacancyId(v ?? "");
              setFrom("");
              setTo("");
            }}
            options={[{ value: "", label: T.noVacancy }, ...published.map((v) => ({ value: v.id, label: `${v.title} · ${v.formats.map((f) => FORMAT_LABEL[f] ?? f).join(", ")}` }))]}
          />
          {vq.isSuccess && published.length === 0 && <span className="text-xs text-muted">{T.noPublished}</span>}
        </div>
      )}
      {!vacancyId && !isInterest && (
        <>
          <label className="flex flex-col gap-1">
            <Lbl>{T.invitation} *</Lbl>
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} aria-invalid={touched && title.trim() === ""} className={fieldClass} />
            <span className={cn("text-xs", touched && title.trim() === "" ? "text-error" : "text-muted")}>{T.invitationHint}</span>
          </label>
          <label className="flex flex-col gap-1">
            <Lbl>{T.invDescription}</Lbl>
            <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} rows={3} className={cn(fieldClass, "h-auto py-2")} />
          </label>
          <div className="flex flex-col gap-1">
            <Lbl>{T.invContact}</Lbl>
            <Select
              aria-label={T.invContact}
              value={contactMethod}
              onChange={(v) => v && setContactMethod(v as ContactMethod)}
              options={Object.values(ContactMethod).map((m) => ({ value: m, label: CONTACT_LABEL[m] ?? m }))}
            />
          </div>
        </>
      )}
      <fieldset className="flex flex-col gap-2">
        <legend className="mb-1">
          <Lbl>{T.range} *</Lbl>
        </legend>
        <SalaryRangeInput
          value={{ from: from ? Number(from) : null, to: to ? Number(to) : null }}
          onChange={(v) => {
            setFrom(v.from == null ? "" : String(v.from));
            setTo(v.to == null ? "" : String(v.to));
          }}
          fromLabel={T.from}
          toLabel={T.to}
          invalid={inputBad}
        />
        <SegmentedControl
          className="self-start"
          label={T.basisLabel}
          value={basis}
          onValueChange={(v) => setBasis(v as SalaryBasis)}
          options={[
            { value: SalaryBasis.gross, label: T.gross },
            { value: SalaryBasis.net, label: T.net },
          ]}
        />
        <p role={rangeBad ? "alert" : undefined} className={cn("text-xs", inputBad ? "text-error" : "text-muted")}>
          {rangeBad ? rangeText : inputBad ? T.wideShort : T.rangeHint}
        </p>
      </fieldset>
      <label className="flex flex-col gap-1">
        <span className="flex items-center justify-between">
          <Lbl>{isInterest ? IT.messageInterest : T.message}</Lbl>
          <Num className="text-xs text-muted">
            {message.length} / {maxMessage}
          </Num>
        </span>
        <textarea value={message} onChange={(e) => setMessage(e.target.value)} maxLength={maxMessage} rows={isInterest ? 3 : 5} placeholder={T.placeholder} className={cn(fieldClass, "h-auto py-2")} />
      </label>
      {!isInterest && (
        <div className="flex flex-col gap-1">
          <Lbl>{T.task}</Lbl>
          <Select
            aria-label={T.task}
            value={familyId}
            onChange={(v) => setFamilyId(v ?? "")}
            options={[{ value: "", label: T.noTask }, ...tasks.map((t) => ({ value: t.family_id, label: t.title }))]}
          />
          {tq.isError && <span className="text-xs text-muted">{T.tasksFail}</span>}
        </div>
      )}

      <section
        aria-label={T.live}
        aria-live="polite"
        className={cn("flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border px-4 py-3", error ? "border-error bg-error-bg" : problem ? "border-dashed border-hairline" : "border-hairline bg-tint-50")}
      >
        {error ? (
          <p role="alert" className="font-mono text-13 font-semibold text-error">
            {T.failed(error instanceof ApiError ? error.status : null)}. {offerErrorText(error)}
          </p>
        ) : problem ? (
          <p className="font-mono text-12 text-muted">{T.liveEmpty}</p>
        ) : level && hint ? (
          <>
            <Num className="text-[22px] font-bold">{Math.round(hint.p_accept * 100)} %</Num>
            <AcceptanceMeter level={level} />
            {upper && (
              <>
                <span aria-hidden className="text-muted">
                  →
                </span>
                <span className="text-13">
                  {T.raise} <b className="font-mono">{formatTh(upper.suggested_salary_to as number)}</b>
                </span>
                <span aria-hidden className="text-muted">
                  →
                </span>
                <Num className="font-bold text-brand-fg">{Math.round((upper.suggested_p_accept as number) * 100)} %</Num>
                <Button type="button" size="sm" variant="outline" onClick={() => setTo(String(upper.suggested_salary_to))}>
                  {IT.apply}
                </Button>
              </>
            )}
          </>
        ) : hintM.isError ? (
          <p role="status" className="text-sm text-muted">
            {T.liveFail}
          </p>
        ) : (
          <div role="status" aria-label={T.liveWait} className="flex items-center gap-3">
            <Skeleton className="h-6 w-14" />
            <Skeleton className="h-3.5 w-36" />
            <Skeleton className="h-6 w-14" />
          </div>
        )}
      </section>

      <div className="flex flex-col gap-1 text-12 text-muted">
        {!problem && hint?.avg_response_hours != null && <p className="font-mono">{IT.respHours(hint.avg_response_hours)}</p>}
        {!problem && hint?.category_median != null && (
          <p>
            {T.median}: <span className="font-mono">{formatRub(hint.category_median)}</span>
          </p>
        )}
        {!problem && expect !== null && hi !== null && <p className={hi < expect ? "text-warning-fg" : "text-success"}>{hi < expect ? T.belowExpect(formatRub(expect)) : T.okExpect(formatRub(expect))}</p>}
        {!problem && wide && <p className="text-warning-fg">{T.wide}</p>}
        <p>{isInterest ? IT.infoInterest : invite ? IT.infoInvite : T.info}</p>
        <p>{T.advice}</p>
      </div>

      <Button type="submit" size="lg" className="w-full" disabled={!canSend || pending}>
        {sendLabel}
      </Button>
    </form>
  );
}

/**
 * Экран C (v2, E38-11): интерес или приглашение в модалке (≥ 1024 px — Dialog, на телефоне — полноэкранный Sheet).
 * Форма монтируется только при открытии: ключ идемпотентности и черновик свежие на каждое открытие.
 * `stay` — после отправки остаться на месте (экран категории): подтверждение в модалке вместо перехода к приглашению.
 * `dark` — хозяин экрана тёмный (карточка кандидата): портал живёт вне его, тему задаём явно.
 */
export function OfferDialog({ open, onOpenChange, candidate, vacancyId = "", alreadyOffered = false, dark = false, mode = "offer", interest, stay = false }: { open: boolean; onOpenChange: (v: boolean) => void; candidate: OfferCandidate; vacancyId?: string; alreadyOffered?: boolean; dark?: boolean; mode?: DialogMode; interest?: OfferForCompany; stay?: boolean }) {
  const desktop = useMedia("(min-width: 1024px)");
  const close = () => onOpenChange(false);
  const title = mode === "interest" ? IT.titleInterest(displayPseudonym(candidate.pseudonym)) : T.title(displayPseudonym(candidate.pseudonym));
  const lead = mode === "interest" ? IT.leadInterest : mode === "invite" ? IT.leadInvite : T.lead;
  const theme = dark ? "dark bg-card text-ink" : "";
  const form = <OfferForm candidate={candidate} vacancyId={vacancyId} alreadyOffered={alreadyOffered} onClose={close} mode={mode} interest={interest} stay={stay} />;
  if (desktop) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className={cn("max-h-[90dvh] max-w-[560px] overflow-y-auto", theme)}>
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
