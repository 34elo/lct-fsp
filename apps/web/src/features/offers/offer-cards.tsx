import { PAGE } from "@/shared/lib/page";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  Button,
  buttonVariants,
  cn,
  EmptyState,
  ErrorState,
  formatRubRangeShort,
  H1,
  InfoTip,
  Panel,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  Skeleton,
  type OfferCardV2Data,
} from "@fsp/ui";

import type { CompanyReliability } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { dayMonth, ratingText } from "@/features/profile/home-model";
import { CAND_TEXT as T, DECLINE_LABEL } from "./text";
import { offerTitle, type CandidateOffer } from "./offer-model";

/** «отвечает в 85 % · 18 ч» из рейтинга ответственности компании; при малой выборке строки нет. */
export function responseNote(r: CompanyReliability | null | undefined): string | undefined {
  if (!r || r.response_rate == null) return undefined;
  const parts = [`отвечает в ${Math.round(r.response_rate * 100)} %`];
  if (r.avg_response_hours != null) parts.push(r.avg_response_hours < 24 ? `${Math.max(1, Math.round(r.avg_response_hours))} ч` : `${Math.round(r.avg_response_hours / 24)} дн.`);
  return parts.join(" · ");
}

/** Приглашение или интерес → данные карточки v2: вилка, срок, задание, «почему ты» (до трёх строк). */
export function offerCardData(o: CandidateOffer, withDeadline = true): OfferCardV2Data {
  return {
    company: o.company.name,
    rating: ratingText(o.company.responsibility_score),
    verified: o.company.verified,
    responseNote: responseNote(o.company.reliability),
    title: offerTitle(o),
    salary: formatRubRangeShort(o.salary_from, o.salary_to),
    salaryNote: o.salary_basis === "net" ? "на руки" : "до НДФЛ",
    task: o.task ? `${o.task.title} · ${o.task.minutes} мин · до ${dayMonth(o.task.deadline_at)}` : undefined,
    reasons: (o.why_you?.factors ?? []).slice(0, 3).map((f) => f.text),
    deadline: withDeadline ? T.deadline(dayMonth(o.expires_at)) : undefined,
  };
}

/** Заголовок экрана и правая сводка (вилки интересов). */
export function ListHeader({ aside, tip }: { aside?: string; tip?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <H1 className="text-[22px] md:text-[26px]">{T.title}</H1>
        {tip && <InfoTip title={T.filter.interests} label={`Что такое «${T.filter.interests}»`}>{tip}</InfoTip>}
      </div>
      {aside && <span className="num text-13">{aside}</span>}
    </div>
  );
}

export const LIST_PAGE = PAGE.normal;

export function ListSkeleton() {
  return (
    <div role="status" aria-label="Загрузка" className="flex flex-col gap-4">
      {[0, 1, 2].map((i) => (
        <Panel key={i} className="flex flex-col gap-2.5">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-[70%]" />
        </Panel>
      ))}
    </div>
  );
}

export function ListError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return <ErrorState title={T.loadError} code={error instanceof ApiError ? T.code(error.status) : undefined} onRetry={onRetry} />;
}

export function ListEmpty({ title, hint }: { title: string; hint?: string }) {
  return <EmptyState title={title} description={hint} action={<Link to="/jobs" className={buttonVariants({ size: "lg" })}>{T.toJobs}</Link>} />;
}

/** Ссылка «Подробнее» на карточку приглашения (переписка, условия). */
export function DetailLink({ id, className }: { id: string; className?: string }) {
  return (
    <Link to={`/me/offers/${id}`} className={cn(buttonVariants({ variant: "ghost" }), "justify-center", className)}>
      {T.details}
    </Link>
  );
}

/** Отказ одним тапом: причина в нижнем листе. */
export function DeclineSheet({
  open,
  reasons,
  pending,
  error,
  hint,
  onPick,
  onClose,
  title,
}: {
  open: boolean;
  reasons: readonly string[];
  pending: boolean;
  error?: string;
  title: string;
  hint: string;
  onPick: (reason: string) => void;
  onClose: () => void;
}) {
  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="bottom" className="mx-auto max-w-lg">
        <SheetTitle className="font-mono text-16">{title}</SheetTitle>
        <SheetDescription>{hint}</SheetDescription>
        <ul className="mt-3 divide-y divide-hairline">
          {reasons.map((r) => (
            <li key={r}>
              <button
                type="button"
                disabled={pending}
                onClick={() => onPick(r)}
                className="flex h-14 w-full items-center justify-between text-left text-14 hover:bg-tint-50 disabled:opacity-50"
              >
                {DECLINE_LABEL[r] ?? r}
                <span aria-hidden className="text-muted">›</span>
              </button>
            </li>
          ))}
        </ul>
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button variant="link" className="mx-auto mt-3 flex" onClick={onClose}>{T.cancel}</Button>
      </SheetContent>
    </Sheet>
  );
}
