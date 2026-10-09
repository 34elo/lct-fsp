import {
  Button,
  Chips,
  GradeScale,
  GradeTag,
  H1,
  Lbl,
  Num,
  Panel,
  PanelCap,
  Skeleton,
  SkillTag,
  StatusTag,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TypeBar,
  buttonVariants,
  cn,
  formatRub,
  formatRubRangeShort,
} from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useState, type ReactNode } from "react";

import {
  getGetAttemptAssessmentAttemptsAttemptIdGetQueryKey,
  getHistoryAssessmentHistoryGetQueryKey,
  useGetAttemptAssessmentAttemptsAttemptIdGet,
  useHistoryAssessmentHistoryGet,
  useUpgradeAssessmentAttemptsAttemptIdUpgradePost,
} from "@/api/endpoints/assessment/assessment";
import { useMyInterestsCandidatesMeInterestsGet } from "@/api/endpoints/offers/offers";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import { ExplainAnswers } from "./Explain";
import {
  GRADE_CUTS,
  holds,
  isFuture,
  latestSurvey,
  lowerGrade,
  seScale,
  skillRows,
  thresholdGrade,
  toScale,
  typeRows,
  validUntil,
} from "./model";
import { GRADE, T, dateShort } from "./text";
import { ErrorLine, LoadError, Page, retryServerOnly } from "./ui";

const dayMonth = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", timeZone: "UTC" }) : "";

/** Скелетон в композиции макета: заголовок, шкала, две колонки. */
function ResultSkeleton() {
  return (
    <div role="status" aria-label={T.loading} className="flex flex-col gap-4" data-testid="assessment-result-loading">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-2/3 max-w-md" />
        <Skeleton className="h-4 w-40" />
      </div>
      <Panel className="flex flex-col gap-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-16" />
      </Panel>
      <div className="grid gap-4 md:grid-cols-12">
        <Panel className="flex flex-col gap-3 md:col-span-5">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-3" />
          ))}
        </Panel>
        <Panel className="flex flex-col gap-3 md:col-span-7">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-20" />
          <Skeleton className="h-20" />
        </Panel>
      </div>
    </div>
  );
}

/**
 * S3: результат теста по макетам v2 (`v2_me-assessment-result__confirmed|not-confirmed`).
 * Красный для «не прошёл» не используется; ключи ответов не показываем.
 */
export default function Result() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  // Попытка в кеше осталась «активной» (последний ответ вернул done без перечитывания): всегда перечитываем.
  const aq = useGetAttemptAssessmentAttemptsAttemptIdGet(id, { query: { retry: retryServerOnly, refetchOnMount: "always" } });
  // Тест завершён: свежая история нужна и здесь (кулдауны), и баннеру пути на Главной (E35-2a).
  const hq = useHistoryAssessmentHistoryGet({ query: { refetchOnMount: "always" } });
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const iq = useMyInterestsCandidatesMeInterestsGet({ query: { retry: false } });
  const nav = useNavigate();
  const invite = useUpgradeAssessmentAttemptsAttemptIdUpgradePost();
  const [later, setLater] = useState(false);
  const [rules, setRules] = useState(false);
  const [topics, setTopics] = useState(false);

  const attempt = aq.data?.status === 200 ? aq.data.data : undefined;
  const history = hq.data?.status === 200 ? hq.data.data : undefined;
  const professions = pq.data?.status === 200 ? pq.data.data.professions : [];
  const interests = iq.data?.status === 200 ? iq.data.data : undefined;

  if (aq.isPending) {
    return (
      <Page wide>
        <ResultSkeleton />
      </Page>
    );
  }
  if (aq.isError || !attempt) {
    return (
      <Page wide>
        <LoadError error={aq.error} onRetry={() => aq.refetch()} />
      </Page>
    );
  }

  if (attempt.status === "active" || !attempt.result) {
    return (
      <Page wide>
        <Panel className="flex flex-col items-start gap-3 p-5" data-testid="assessment-active">
          <H1 className="max-md:text-[22px]">{T.inProgress}</H1>
          <p className="text-14 text-muted">{T.inProgressText}</p>
          <Link to={`/me/assessment/attempts/${id}`} className={buttonVariants()} data-testid="assessment-continue">
            {T.continueTest}
          </Link>
        </Panel>
      </Page>
    );
  }

  const r = attempt.result;
  const title = professions.find((p) => p.slug === attempt.profession)?.title ?? attempt.profession;
  const grade = r.grade ?? null;
  const gradeLabel = (g: string) => GRADE[g] ?? g;
  const declared = gradeLabel(attempt.declared_grade);
  const category = `${title} · ${grade ? gradeLabel(grade) : declared}`;
  const rows = skillRows(r.by_skill);
  const types = typeRows(r.theta_by_type);
  const integrity = r.integrity ?? 1;
  const until = validUntil(attempt.finished_at);
  const express = attempt.mode === "express";
  const nextChange = history?.cooldowns.find((c) => c.profession === attempt.profession && isFuture(c.next_change_at));
  const retry = history?.retries?.find((c) => c.profession === attempt.profession && isFuture(c.next_attempt_at));
  const survey = history ? latestSurvey(history.surveys, attempt.profession) : null;
  // Порог шкалы: подтверждён — следующий грейд, не подтверждён — заявленный.
  const thr = thresholdGrade(grade, attempt.declared_grade);
  const cut = toScale(GRADE_CUTS[thr] ?? 0);
  const score = typeof r.theta === "number" ? toScale(r.theta) : null;
  // ADR-025 п.2: бонусный этап приглашает на отдельный тест следующего грейда, а не повышает.
  const invited = attempt.invited_grade ?? null;
  const inviteLive = !!invited && (!attempt.invite_expires_at || isFuture(attempt.invite_expires_at));
  const invitedAttempt = attempt.invite_attempt_id ?? null;
  const lower = grade ? null : lowerGrade(attempt.declared_grade);

  const startInvited = () =>
    invite.mutate(
      { attemptId: id },
      {
        onSuccess: (res) => {
          void qc.invalidateQueries({ queryKey: getGetAttemptAssessmentAttemptsAttemptIdGetQueryKey(id) });
          void qc.invalidateQueries({ queryKey: getHistoryAssessmentHistoryGetQueryKey() });
          if (res.status === 201) nav(`/me/assessment/attempts/${res.data.id}`);
        },
      },
    );

  const full = "max-md:w-full";
  const home = (primary: boolean) => (
    <Link to="/me" className={cn(buttonVariants({ size: "lg", variant: primary ? "default" : "outline" }), full)} data-testid="assessment-to-profile">
      {T.openProfile}
    </Link>
  );

  // Второе действие шапки: тест следующего грейда по приглашению, приглашения или тест ниже (макет).
  let second: ReactNode = null;
  if (grade && invited && invitedAttempt) {
    second = (
      <Link
        to={`/me/assessment/attempts/${invitedAttempt}`}
        className={cn(buttonVariants({ size: "lg", variant: "outline" }), full)}
        data-testid="assessment-invite-open"
      >
        {T.inviteOpen}
      </Link>
    );
  } else if (grade && inviteLive) {
    second = (
      <Button size="lg" variant="outline" className={full} loading={invite.isPending} onClick={startInvited} data-testid="assessment-invite-start">
        {T.passGrade(gradeLabel(invited!))}
      </Button>
    );
  } else if (grade) {
    second = (
      <Link to="/me/offers" className={cn(buttonVariants({ size: "lg", variant: "outline" }), full)} data-testid="assessment-to-offers">
        {T.toOffers}
      </Link>
    );
  }

  return (
    <Page wide>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <H1 className="max-md:text-[22px] max-md:leading-[1.2]" data-testid="assessment-grade">
            {grade ? T.confirmedTitle(category) : T.notConfirmedTitle(declared)}
          </H1>
          <div className="flex flex-wrap items-center gap-2" data-testid={grade ? "assessment-confirmed" : "assessment-not-confirmed"}>
            {!grade && <GradeTag claimed>{category}</GradeTag>}
            {express && <StatusTag data-testid="assessment-express">{T.expressBadge}</StatusTag>}
            {attempt.finished_at && <Num className="text-12">{dayMonth(attempt.finished_at)}</Num>}
            <button
              type="button"
              aria-label={T.howItWorks}
              aria-expanded={rules}
              onClick={() => setRules((v) => !v)}
              className="inline-flex h-7 min-w-7 items-center justify-center rounded-full bg-tint-100 px-2 font-mono text-12 font-semibold text-brand-fg max-md:h-8 max-md:min-w-8"
              data-testid="assessment-rules-toggle"
            >
              ?
            </button>
          </div>
        </div>
        <div className="flex items-center gap-3 max-md:w-full max-md:flex-col-reverse max-md:items-stretch">
          {grade ? (
            <>
              {second}
              {home(true)}
            </>
          ) : lower ? (
            <>
              <span className="text-13 text-muted max-md:hidden">{T.lowerHint(gradeLabel(lower))}</span>
              {home(false)}
              <Link
                to={`/me/assessment?profession=${encodeURIComponent(attempt.profession)}&grade=${lower}`}
                className={cn(buttonVariants({ size: "lg" }), full)}
                data-testid="assessment-lower"
              >
                {T.startLower(gradeLabel(lower))}
              </Link>
            </>
          ) : (
            <>
              <Link to="/me/navigator" className={cn(buttonVariants({ size: "lg", variant: "outline" }), full)} data-testid="assessment-growth-cta">
                {T.openGrowth}
              </Link>
              {home(true)}
            </>
          )}
        </div>
      </header>

      {rules && (
        <Panel className="flex flex-col gap-2 bg-tint-50 text-14" data-testid="assessment-rules">
          <Lbl>{T.howItWorks}</Lbl>
          <ul className="flex list-disc flex-col gap-1 pl-5">
            {T.rulesList.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
          <p className="text-13 text-muted">{T.cooldownRules}</p>
        </Panel>
      )}

      {invited && !invitedAttempt && inviteLive && !later && (
        <Panel selected className="flex flex-col gap-2" data-testid="assessment-invite">
          <Lbl>{T.inviteTitle}</Lbl>
          <h2 className="m-0 font-mono text-16 font-semibold">{T.inviteAvailable(`${gradeLabel(invited)} · ${title}`)}</h2>
          <p className="text-14 text-muted">{T.inviteText}</p>
          {attempt.invite_expires_at && (
            <p className="text-13 text-muted" data-testid="assessment-invite-until">
              {T.inviteUntil(dateShort(attempt.invite_expires_at))}
            </p>
          )}
          {invite.isError && <ErrorLine error={invite.error} data-testid="assessment-invite-error" />}
          <div className="flex flex-wrap gap-2">
            {!grade && (
              <Button loading={invite.isPending} onClick={startInvited} data-testid="assessment-invite-start">
                {T.inviteStart(gradeLabel(invited))}
              </Button>
            )}
            <Button variant="ghost" disabled={invite.isPending} onClick={() => setLater(true)} data-testid="assessment-invite-later">
              {T.inviteLater}
            </Button>
          </div>
        </Panel>
      )}
      {later && (
        <p role="status" className="text-13 text-muted" data-testid="assessment-invite-later-text">
          {T.inviteLaterText}
        </p>
      )}
      {invited && !invitedAttempt && !inviteLive && (
        <p className="text-13 text-muted" data-testid="assessment-invite-expired">
          {T.inviteExpired}
        </p>
      )}
      {attempt.invited_by && (
        <p className="text-13 text-muted" data-testid="assessment-invited-attempt">
          {T.invitedAttempt}
        </p>
      )}

      <Panel data-testid="assessment-summary">
        <PanelCap
          title={T.scaleTitle}
          aside={
            score !== null && (
              <Lbl className="text-right" data-testid="assessment-scale-aside">
                <span className="max-md:hidden">{T.scaleAside(score, gradeLabel(thr), cut)}</span>
                <span className="md:hidden">{T.scaleAsideShort(score, cut)}</span>
              </Lbl>
            )
          }
        />
        {score !== null ? (
          <GradeScale value={score} error={seScale(r.se)} />
        ) : (
          <p className="text-14 text-muted">{T.scaleNoData}</p>
        )}
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-13 text-muted">
          <div className="flex items-baseline gap-1.5">
            <dt>{T.tasks}</dt>
            <dd className="num text-ink" data-testid="assessment-count">
              {attempt.answered}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt>{T.confidence}</dt>
            <dd className="num text-ink" data-testid="assessment-confidence">
              {attempt.low_confidence ? T.confidenceLow : T.confidenceHigh}
            </dd>
          </div>
          <div className="flex items-baseline gap-1.5">
            <dt>{T.integrity}</dt>
            <dd className="num text-ink" data-testid="assessment-integrity">
              {integrity.toFixed(2)}
            </dd>
          </div>
          {grade && until && <div>{T.validUntil(dateShort(until))}</div>}
        </dl>
        <div className="mt-2 flex flex-col gap-1.5 text-13 text-muted empty:hidden">
          {express && <p>{T.expressResult}</p>}
          {!grade && <p>{T.failedText}</p>}
          {attempt.low_confidence && <p>{T.lowConfidence}</p>}
          {r.needs_confirmation && (
            <p className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-warning-fg" data-testid="assessment-needs-confirmation">
              {T.needsConfirmation}
            </p>
          )}
        </div>
      </Panel>

      <div className="grid items-start gap-4 md:grid-cols-12">
        <div className="flex min-w-0 flex-col gap-4 md:col-span-5">
          {types.length > 0 && (
            <Panel data-testid="assessment-types">
              <PanelCap
                title={T.typesTitle}
                aside={
                  <Lbl>
                    <span className="max-md:hidden">{T.typesAside(gradeLabel(thr))}</span>
                    <span className="md:hidden">{T.typesAsideShort}</span>
                  </Lbl>
                }
              />
              <TypeBar threshold={cut} items={types.map((t) => ({ label: T.types[t.type] ?? t.type, value: t.value }))} />
            </Panel>
          )}

          {grade ? (
            <Panel className="flex flex-col gap-3" data-testid="assessment-opened">
              <Lbl>{T.opened}</Lbl>
              {interests && (
                <div className="flex items-end gap-3">
                  <Num className="text-[40px] leading-none max-md:text-[36px]" data-testid="assessment-opened-count">
                    {interests.companies}
                  </Num>
                  <span className="pb-[3px] text-14">{T.openedInterests(interests.companies)}</span>
                </div>
              )}
              <p className="text-14">{T.openedCategory(category)}</p>
              {interests?.salary_from_min != null && interests.salary_to_max != null && (
                <Num className="text-12">{formatRubRangeShort(interests.salary_from_min, interests.salary_to_max)}</Num>
              )}
            </Panel>
          ) : (
            survey &&
            ((survey.stack?.length ?? 0) > 0 || survey.salary_from != null) && (
              <Panel className="flex flex-col gap-3" data-testid="assessment-claimed">
                <Lbl>{T.claimedTitle}</Lbl>
                {(survey.stack?.length ?? 0) > 0 && (
                  <Chips>
                    {survey.stack!.map((s) => (
                      <SkillTag key={s} name={s} state="claimed" level={0} />
                    ))}
                  </Chips>
                )}
                {survey.salary_from != null && (
                  <div className="text-13 text-muted">
                    {T.claimedSalary} <Num className="text-ink">{formatRub(survey.salary_from)}</Num>
                  </div>
                )}
              </Panel>
            )
          )}

          {rows.length > 0 && (
            <Panel className="p-0">
              <button
                type="button"
                aria-expanded={topics}
                aria-controls="assessment-skills"
                onClick={() => setTopics((v) => !v)}
                className="flex w-full items-center justify-between gap-3 rounded-xl p-4 text-left font-semibold"
                data-testid="assessment-topics-toggle"
              >
                <span>{T.topics}</span>
                <Num className="text-muted">
                  {rows.length} {topics ? "⌄" : "›"}
                </Num>
              </button>
              {topics && (
                <div id="assessment-skills" className="flex flex-col gap-2 border-t border-hairline p-4">
                  <p className="text-13 text-muted">{T.bySkillLead}</p>
                  <div className="overflow-x-auto">
                    <Table data-testid="assessment-skills">
                      <TableHeader>
                        <TableRow>
                          <TableHead>{T.colSkill}</TableHead>
                          <TableHead>{T.colItems}</TableHead>
                          <TableHead>{T.colShare}</TableHead>
                          <TableHead>{T.colTrust}</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {rows.map((s) => (
                          <TableRow key={s.skill} data-testid={`assessment-skill-${s.skill}`}>
                            <TableCell className="font-mono">{s.skill}</TableCell>
                            <TableCell>{s.items}</TableCell>
                            <TableCell>{Math.round(s.share * 100)}%</TableCell>
                            <TableCell>
                              <StatusTag state={holds(s.share) ? "ok" : "claimed"}>{holds(s.share) ? T.holds : T.improve}</StatusTag>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}
            </Panel>
          )}

          <Link
            to={`/me/assessment/attempts/${id}/review`}
            className="flex items-center justify-between gap-3 rounded-xl border border-hairline bg-card p-4 font-semibold"
            data-testid="assessment-to-review"
          >
            <span>{T.review.link}</span>
            <Num className="text-muted">›</Num>
          </Link>

          <Link
            to="/me/navigator"
            className="flex items-center justify-between gap-3 rounded-xl border border-hairline bg-card p-4 font-semibold"
            data-testid="assessment-to-growth"
          >
            <span>{T.growthLink}</span>
            <Num className="text-muted">›</Num>
          </Link>

          {(nextChange || retry) && (
            <Panel className="flex flex-col gap-1 text-14" data-testid="assessment-cooldown">
              {nextChange && <p className="font-semibold">{T.nextChange(dateShort(nextChange.next_change_at))}</p>}
              {retry && <p className="font-semibold">{T.retryAt(gradeLabel(retry.grade), dateShort(retry.next_attempt_at))}</p>}
              <Link to="/me/assessment/history" className="text-13 font-semibold text-brand-fg underline" data-testid="assessment-to-history">
                {T.toHistory}
              </Link>
            </Panel>
          )}
        </div>

        <ExplainAnswers attemptId={id} answers={r.answers} className="md:col-span-7" />
      </div>
    </Page>
  );
}
