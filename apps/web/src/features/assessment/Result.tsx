import { Badge, Button, Card, GradeBadge, SectionLabel, Skeleton, Table, TableBody, TableCell, TableHead, TableHeader, TableRow, buttonVariants } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { useState } from "react";

import {
  getGetAttemptAssessmentAttemptsAttemptIdGetQueryKey,
  getHistoryAssessmentHistoryGetQueryKey,
  useGetAttemptAssessmentAttemptsAttemptIdGet,
  useHistoryAssessmentHistoryGet,
  useUpgradeAssessmentAttemptsAttemptIdUpgradePost,
} from "@/api/endpoints/assessment/assessment";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import { holds, isFuture, skillRows, validUntil } from "./model";
import { GRADE, T, dateShort } from "./text";
import { ErrorLine, LoadError, Page, retryServerOnly } from "./ui";

/** S3: результат. Красный для «не прошёл» не используется; ключи ответов не показываем. */
export default function Result() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const aq = useGetAttemptAssessmentAttemptsAttemptIdGet(id, { query: { retry: retryServerOnly } });
  const hq = useHistoryAssessmentHistoryGet();
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const upgrade = useUpgradeAssessmentAttemptsAttemptIdUpgradePost();
  const [kept, setKept] = useState(false);

  const attempt = aq.data?.status === 200 ? aq.data.data : undefined;
  const history = hq.data?.status === 200 ? hq.data.data : undefined;
  const professions = pq.data?.status === 200 ? pq.data.data.professions : [];

  if (aq.isPending) {
    return (
      <Page>
        <div role="status" aria-label={T.loading} className="flex flex-col gap-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-48" />
        </div>
      </Page>
    );
  }
  if (aq.isError || !attempt) {
    return (
      <Page>
        <LoadError error={aq.error} onRetry={() => aq.refetch()} />
      </Page>
    );
  }

  if (attempt.status === "active" || !attempt.result) {
    return (
      <Page>
        <Card className="flex flex-col items-start gap-3 p-5" data-testid="assessment-active">
          <h1 className="font-mono text-2xl font-semibold">{T.inProgress}</h1>
          <p className="text-14 text-muted">{T.inProgressText}</p>
          <Link to={`/me/assessment/attempts/${id}`} className={buttonVariants()} data-testid="assessment-continue">
            {T.continueTest}
          </Link>
        </Card>
      </Page>
    );
  }

  const r = attempt.result;
  const title = professions.find((p) => p.slug === attempt.profession)?.title ?? attempt.profession;
  const grade = r.grade ?? null;
  const rows = skillRows(r.by_skill);
  const integrity = r.integrity ?? 1;
  const until = validUntil(attempt.finished_at);
  const nextChange = history?.cooldowns.find((c) => c.profession === attempt.profession && isFuture(c.next_change_at));
  const retry = history?.retries?.find((c) => c.profession === attempt.profession && isFuture(c.next_attempt_at));
  const offer = attempt.upgrade_offer && !attempt.upgrade_accepted ? attempt.upgrade_offer : null;

  const accept = () =>
    upgrade.mutate(
      { attemptId: id },
      {
        onSuccess: () => {
          void qc.invalidateQueries({ queryKey: getGetAttemptAssessmentAttemptsAttemptIdGetQueryKey(id) });
          void qc.invalidateQueries({ queryKey: getHistoryAssessmentHistoryGetQueryKey() });
        },
      },
    );

  return (
    <Page>
      <header className="flex flex-col gap-1">
        <SectionLabel>
          {T.resultTitle} · {title}
        </SectionLabel>
        <h1 className="font-mono text-2xl font-semibold" data-testid="assessment-grade">
          {grade ? (GRADE[grade] ?? grade) : T.failedTitle}
        </h1>
      </header>

      <Card className="flex flex-col gap-4 p-5" data-testid="assessment-summary">
        <div className="flex flex-wrap items-center gap-3">
          {grade ? (
            <>
              <GradeBadge grade={GRADE[grade] ?? grade} role={title} />
              <Badge variant="success" data-testid="assessment-confirmed">
                {T.confirmed}
              </Badge>
            </>
          ) : (
            <Badge variant="muted" data-testid="assessment-not-confirmed">
              {T.notConfirmed}
            </Badge>
          )}
        </div>
        {grade && until && <p className="text-14 text-muted">{T.validUntil(dateShort(until))}</p>}
        {!grade && <p className="text-14 text-muted">{T.failedText}</p>}
        <dl className="grid grid-cols-3 gap-3 text-center">
          <div>
            <dd className="font-mono text-24 font-semibold" data-testid="assessment-count">
              {attempt.answered}
            </dd>
            <dt className="text-12 text-muted">{T.tasks}</dt>
          </div>
          <div>
            <dd className="font-mono text-24 font-semibold" data-testid="assessment-confidence">
              {attempt.low_confidence ? T.confidenceLow : T.confidenceHigh}
            </dd>
            <dt className="text-12 text-muted">{T.confidence}</dt>
          </div>
          <div>
            <dd className="font-mono text-24 font-semibold" data-testid="assessment-integrity">
              {integrity.toFixed(2)}
            </dd>
            <dt className="text-12 text-muted">{T.integrity}</dt>
          </div>
        </dl>
        {attempt.low_confidence && <p className="text-13 text-muted">{T.lowConfidence}</p>}
        {r.needs_confirmation && (
          <p className="rounded-lg border border-warning-border bg-warning-bg px-3 py-2 text-13 text-warning-fg">{T.needsConfirmation}</p>
        )}
      </Card>

      {attempt.upgrade_accepted && (
        <p role="status" className="rounded-lg bg-success-bg px-3 py-2 text-14 text-success" data-testid="assessment-upgrade-done">
          {T.upgradeDone}
        </p>
      )}
      {offer && !kept && (
        <Card className="flex flex-col gap-3 border-brand p-5" data-testid="assessment-upgrade">
          <SectionLabel>{T.upgradeTitle}</SectionLabel>
          <h2 className="text-18 font-semibold">
            {T.upgradeAvailable(`${GRADE[offer] ?? offer} · ${title}`)}
          </h2>
          <p className="text-14 text-muted">{T.upgradeText}</p>
          {upgrade.isError && <ErrorLine error={upgrade.error} data-testid="assessment-upgrade-error" />}
          <div className="flex flex-wrap gap-2">
            <Button loading={upgrade.isPending} onClick={accept} data-testid="assessment-upgrade-accept">
              {T.upgradeAccept(GRADE[offer] ?? offer)}
            </Button>
            <Button variant="outline" disabled={upgrade.isPending} onClick={() => setKept(true)} data-testid="assessment-upgrade-keep">
              {T.upgradeKeep(grade ? (GRADE[grade] ?? grade) : GRADE[attempt.declared_grade]!)}
            </Button>
          </div>
        </Card>
      )}
      {kept && (
        <p role="status" className="text-13 text-muted" data-testid="assessment-upgrade-kept">
          {T.upgradeKept}
        </p>
      )}

      <section className="flex flex-col gap-2" aria-labelledby="assessment-by-skill">
        <SectionLabel id="assessment-by-skill">{T.bySkill}</SectionLabel>
        <p className="text-13 text-muted">{T.bySkillLead}</p>
        {rows.length > 0 && (
          <Card className="overflow-x-auto">
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
                      <Badge variant={holds(s.share) ? "success" : "warning"}>{holds(s.share) ? T.holds : T.improve}</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </section>

      <Card className="flex flex-col gap-2 p-4 text-14" data-testid="assessment-cooldown">
        {nextChange && <p className="font-semibold">{T.nextChange(dateShort(nextChange.next_change_at))}</p>}
        {retry && <p className="font-semibold">{T.retryAt(GRADE[retry.grade] ?? retry.grade, dateShort(retry.next_attempt_at))}</p>}
        <p className="text-13 text-muted">{T.cooldownRules}</p>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Link to="/me" className={buttonVariants()} data-testid="assessment-to-profile">
          {T.openProfile}
        </Link>
        <Link to="/me/growth" className={buttonVariants({ variant: "outline" })} data-testid="assessment-to-growth">
          {T.openGrowth}
        </Link>
        <Link to="/me/assessment/history" className={buttonVariants({ variant: "ghost" })} data-testid="assessment-to-history">
          {T.toHistory}
        </Link>
      </div>
    </Page>
  );
}
