import {
  Badge,
  Card,
  EmptyState,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  buttonVariants,
} from "@fsp/ui";
import { Link } from "react-router-dom";

import { useHistoryAssessmentHistoryGet } from "@/api/endpoints/assessment/assessment";
import { useGetProfessionsTaxonomyProfessionsGet } from "@/api/endpoints/taxonomy/taxonomy";
import type { AttemptOut, SurveyOut } from "@/api/model";
import { isFuture } from "./model";
import { GRADE, T, dateShort } from "./text";
import { LoadError, Page } from "./ui";

function outcome(a: AttemptOut): { label: string; variant: "success" | "muted" | "warning" | "default" } {
  if (a.status === "active") return { label: T.active, variant: "default" };
  if (a.status === "abandoned") return { label: T.abandoned, variant: "muted" };
  if (a.low_confidence) return { label: T.lowConf, variant: "warning" };
  return a.status === "passed" ? { label: T.passed, variant: "success" } : { label: T.failed, variant: "muted" };
}

const salary = (s: SurveyOut) =>
  s.salary_from || s.salary_to ? `${(s.salary_from ?? 0).toLocaleString("ru-RU")}–${(s.salary_to ?? 0).toLocaleString("ru-RU")} ₽` : "—";

function CooldownCard({ title, tag, text, until, to }: { title: string; tag: string; text: string; until: string; to: string }) {
  const locked = isFuture(until);
  return (
    <Card className="flex flex-col gap-2 p-4" data-testid="assessment-cooldown-card" data-locked={locked}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-16 font-semibold">{title}</h3>
        <Badge variant={locked ? "warning" : "success"}>{locked ? tag : T.availableNow}</Badge>
      </div>
      <p className="text-13 text-muted">{text}</p>
      {locked ? (
        <span aria-disabled="true" className={buttonVariants({ variant: "outline", className: "pointer-events-none opacity-50" })} data-testid="assessment-cooldown-locked">
          {T.until(dateShort(until))}
        </span>
      ) : (
        <Link to={to} className={buttonVariants()} data-testid="assessment-cooldown-go">
          {T.newAttempt}
        </Link>
      )}
    </Card>
  );
}

/** S4: история попыток, кулдауны и пересдачи. */
export default function History() {
  const hq = useHistoryAssessmentHistoryGet();
  const pq = useGetProfessionsTaxonomyProfessionsGet();
  const h = hq.data?.status === 200 ? hq.data.data : undefined;
  const professions = pq.data?.status === 200 ? pq.data.data.professions : [];
  const name = (slug: string | null | undefined) => professions.find((p) => p.slug === slug)?.title ?? slug ?? "—";

  return (
    <Page wide>
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-mono text-2xl font-semibold">{T.historyTitle}</h1>
        <Link to="/me/assessment" className={buttonVariants()} data-testid="assessment-new">
          {T.newAttempt}
        </Link>
      </header>

      {hq.isPending ? (
        <div role="status" aria-label={T.loading} className="flex flex-col gap-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-40" />
        </div>
      ) : hq.isError || !h ? (
        <LoadError error={hq.error} onRetry={() => hq.refetch()} />
      ) : (
        <>
          <section className="flex flex-col gap-2" aria-label={T.cooldownTitle} data-testid="assessment-cooldowns">
            {h.cooldowns.length === 0 && !(h.retries?.length ?? 0) ? (
              <p className="text-14 text-muted">{T.noCooldowns}</p>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
                {h.cooldowns.map((c) => (
                  <CooldownCard
                    key={`c-${c.profession}`}
                    title={`${name(c.profession)} · ${GRADE[c.grade] ?? c.grade}`}
                    tag={T.cooldown90}
                    text={`${T.change90} ${T.nextChange(dateShort(c.next_change_at))}.`}
                    until={c.next_change_at}
                    to={`/me/assessment?profession=${c.profession}&grade=${c.grade}`}
                  />
                ))}
                {(h.retries ?? []).map((r) => (
                  <CooldownCard
                    key={`r-${r.profession}-${r.grade}`}
                    title={`${name(r.profession)} · ${GRADE[r.grade] ?? r.grade}`}
                    tag={T.cooldown30}
                    text={T.retry30}
                    until={r.next_attempt_at}
                    to={`/me/assessment?profession=${r.profession}&grade=${r.grade}`}
                  />
                ))}
              </div>
            )}
          </section>

          <Tabs defaultValue="attempts">
            <TabsList>
              <TabsTrigger value="attempts" count={h.attempts.length} data-testid="assessment-tab-attempts">
                {T.attemptsTab}
              </TabsTrigger>
              <TabsTrigger value="surveys" count={h.surveys.length} data-testid="assessment-tab-surveys">
                {T.surveysTab}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="attempts" className="pt-3">
              {h.attempts.length === 0 ? (
                <EmptyState
                  title={T.emptyAttempts}
                  description={T.emptyAttemptsText}
                  action={
                    <Link to="/me/assessment" className={buttonVariants()}>
                      {T.newAttempt}
                    </Link>
                  }
                />
              ) : (
                <Card className="overflow-x-auto">
                  <Table data-testid="assessment-attempts">
                    <TableHeader>
                      <TableRow>
                        <TableHead>{T.colDate}</TableHead>
                        <TableHead>{T.colProfession}</TableHead>
                        <TableHead>{T.colResult}</TableHead>
                        <TableHead>{T.tasks}</TableHead>
                        <TableHead>{T.colIntegrity}</TableHead>
                        <TableHead />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {h.attempts.map((a) => {
                        const o = outcome(a);
                        return (
                          <TableRow key={a.id} data-testid={`assessment-attempt-${a.id}`}>
                            <TableCell>{dateShort(a.finished_at ?? a.started_at)}</TableCell>
                            <TableCell>
                              {name(a.profession)} · {GRADE[a.declared_grade] ?? a.declared_grade}
                              {a.mode === "express" && (
                                <Badge variant="dashed" className="ml-2">
                                  {T.expressBadge}
                                </Badge>
                              )}
                            </TableCell>
                            <TableCell>
                              <Badge variant={o.variant}>{o.label}</Badge>
                            </TableCell>
                            <TableCell>{a.answered}</TableCell>
                            <TableCell>{a.result?.integrity != null ? a.result.integrity.toFixed(2) : "—"}</TableCell>
                            <TableCell>
                              <Link
                                to={a.status === "active" ? `/me/assessment/attempts/${a.id}` : `/me/assessment/attempts/${a.id}/result`}
                                className="font-semibold text-brand-fg underline"
                                data-testid={`assessment-attempt-link-${a.id}`}
                              >
                                {a.status === "active" ? T.continueTest : T.breakdown}
                              </Link>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="surveys" className="pt-3">
              {h.surveys.length === 0 ? (
                <EmptyState title={T.emptySurveys} />
              ) : (
                <Card className="overflow-x-auto">
                  <Table data-testid="assessment-surveys">
                    <TableHeader>
                      <TableRow>
                        <TableHead>{T.colDate}</TableHead>
                        <TableHead>{T.colProfession}</TableHead>
                        <TableHead>{T.colSalary}</TableHead>
                        <TableHead>{T.colStack}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {h.surveys.map((s, i) => (
                        <TableRow key={s.id ?? i}>
                          <TableCell>{dateShort(s.created_at)}</TableCell>
                          <TableCell>
                            {name(s.profession)}
                            {s.declared_grade ? ` · ${GRADE[s.declared_grade] ?? s.declared_grade}` : ""}
                          </TableCell>
                          <TableCell>{salary(s)}</TableCell>
                          <TableCell className="font-mono text-12">{(s.stack ?? []).join(", ") || "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </>
      )}
    </Page>
  );
}
