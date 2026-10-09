import { Badge, Button, CodeLines, H1, Lbl, Markdown, Num, Panel, PanelCap, Skeleton, SkillTag, Switch, buttonVariants, cn } from "@fsp/ui";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useReviewAttemptAssessmentAttemptsAttemptIdReviewGet } from "@/api/endpoints/assessment/assessment";
import type { ReviewItemOut, ReviewPartOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { groupByType, loadHideExplain, parseListing, saveHideExplain, splitStem, verdict, weakSkills } from "./model";
import { T } from "./text";
import { LoadError, Page, retryServerOnly } from "./ui";

const R = T.review;
const VARIANT = { ok: "success", part: "warning", bad: "muted" } as const;

/** Условие: текст через Markdown (таблицы), код — моноширинным блоком. */
function Stem({ part }: { part: ReviewPartOut }) {
  if (part.kind === "find_bug") {
    const { prose, lines } = parseListing(part.stem);
    return (
      <div className="flex flex-col gap-2">
        <Markdown>{prose}</Markdown>
        {lines.length > 0 && <CodeLines lines={lines.map((l) => l.text)} start={lines[0]!.no} label="Код задания" />}
      </div>
    );
  }
  const { prose, code } = splitStem(part.stem);
  return (
    <div className="flex flex-col gap-2">
      <Markdown>{prose}</Markdown>
      {code && <CodeLines lines={code.split("\n")} label="Код задания" />}
    </div>
  );
}

/** Ответ кандидата; верных ответов и вариантов разбор не показывает (E41-5); у `find_bug` подпись «строки». */
function Answers({ part, testId }: { part: ReviewPartOut; testId: string }) {
  const unit = part.kind === "find_bug" ? `${R.lines}: ` : "";
  return (
    <dl className="m-0 text-14">
      <div className="min-w-0 rounded-lg bg-tint-50 p-3">
        <dt>
          <Lbl>{R.yours}</Lbl>
        </dt>
        <dd className="m-0 mt-1 font-mono break-words" data-testid={`${testId}-yours`}>
          {part.yours ? `${unit}${part.yours}` : <span className="text-muted">{R.noAnswer}</span>}
        </dd>
      </div>
    </dl>
  );
}

/** Объяснение с собственным сворачиванием; общий переключатель скрывает его целиком. */
function Why({ item, hidden, testId }: { item: ReviewItemOut; hidden: boolean; testId: string }) {
  const [open, setOpen] = useState(true);
  if (hidden) return null;
  return (
    <div className="flex flex-col gap-2" data-testid={`${testId}-why`}>
      <Button size="sm" variant="link" className="w-fit px-0 no-underline" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`${testId}-toggle`}>
        {open ? R.collapse : R.expand}
      </Button>
      {open && (
        <div className="flex flex-col gap-2 rounded-lg border border-hairline p-3 text-14">
          <p className="flex flex-wrap items-center gap-2">
            <span className="text-13 text-muted">{R.why}</span>
            <b className="font-semibold">{item.reason.label}</b>
          </p>
          <p>{item.why}</p>
          {item.steps?.map((s, i) => (
            <p key={i} className="text-13 text-muted">
              <b>{R.step(i + 1)}:</b> {s.reason.label}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function Task({ item, hidden }: { item: ReviewItemOut; hidden: boolean }) {
  const v = verdict(item.score);
  const id = `assessment-review-item-${item.seq}`;
  return (
    <article className="flex flex-col gap-3 border-t border-hairline pt-4 first:border-t-0 first:pt-0" data-testid={id} data-verdict={v}>
      <header className="flex flex-wrap items-center gap-2">
        <b className="font-semibold">{R.task(item.seq)}</b>
        <SkillTag name={item.skill} />
        <Badge variant={VARIANT[v]} data-testid={`${id}-verdict`}>
          {R.verdict[v]}
        </Badge>
      </header>
      <div className="flex flex-col gap-1">
        <Lbl>{R.asked}</Lbl>
        <Stem part={item} />
      </div>
      {item.steps ? (
        <ol className="m-0 flex list-none flex-col gap-3 p-0">
          {item.steps.map((s, i) => (
            <li key={i} className="flex flex-col gap-2 rounded-lg border border-hairline p-3">
              <b className="text-13">{R.step(i + 1)}</b>
              <Stem part={s} />
              <Answers part={s} testId={`${id}-step-${i + 1}`} />
            </li>
          ))}
        </ol>
      ) : (
        <Answers part={item} testId={id} />
      )}
      <Why item={item} hidden={hidden} testId={id} />
    </article>
  );
}

/** «Что подтянуть»: навыки с неполным баллом и ссылка в навигатор роста. */
function Brush({ items }: { items: ReviewItemOut[] }) {
  const weak = weakSkills(items);
  return (
    <Panel className="flex flex-col gap-3" data-testid="assessment-review-brush">
      <PanelCap title={<h2 className="m-0 font-mono text-16 leading-[1.3] font-semibold">{R.brushTitle}</h2>} />
      {weak.length === 0 ? (
        <p className="text-14 text-muted">{R.brushNone}</p>
      ) : (
        <>
          <p className="text-13 text-muted">{R.brushLead}</p>
          <ul className="m-0 flex list-none flex-col gap-2 p-0">
            {weak.map((w) => (
              <li key={w.skill} className="flex items-center gap-2" data-testid={`assessment-review-weak-${w.skill}`}>
                <SkillTag name={w.skill} state="claimed" />
                <Num className="text-12 text-muted">{R.missed(w.missed)}</Num>
              </li>
            ))}
          </ul>
        </>
      )}
      <Link to="/me/navigator" className={cn(buttonVariants({ variant: weak.length ? "default" : "outline" }), "w-fit")} data-testid="assessment-review-to-growth">
        {R.brushGo}
      </Link>
    </Panel>
  );
}

/** Разбор теста (E39-10): задания по типам навыков, переключатель «Скрыть объяснения» с запоминанием. */
export default function Review() {
  const { id = "" } = useParams();
  const q = useReviewAttemptAssessmentAttemptsAttemptIdReviewGet(id, { query: { retry: retryServerOnly } });
  const [hidden, setHidden] = useState(loadHideExplain);
  const data = q.data?.status === 200 ? q.data.data : undefined;

  const toggle = (v: boolean) => {
    setHidden(v);
    saveHideExplain(v);
  };

  if (q.isPending) {
    return (
      <Page wide>
        <div role="status" aria-label={T.loading} className="flex flex-col gap-4" data-testid="assessment-review-loading">
          <Skeleton className="h-7 w-1/2 max-w-md" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      </Page>
    );
  }
  if (q.isError || !data) {
    if (q.error instanceof ApiError && q.error.status === 409) {
      return (
        <Page wide>
          <Panel className="flex flex-col items-start gap-3 p-5" data-testid="assessment-review-active">
            <H1 className="max-md:text-[22px]">{R.activeTitle}</H1>
            <p className="text-14 text-muted">{R.activeText}</p>
            <Link to={`/me/assessment/attempts/${id}`} className={buttonVariants()}>
              {T.continueTest}
            </Link>
          </Panel>
        </Page>
      );
    }
    return (
      <Page wide>
        <LoadError error={q.error} onRetry={() => q.refetch()} />
      </Page>
    );
  }

  const rows = data.items.map((i) => ({ ...i, type: i.skill_type }));
  const groups = groupByType(rows);
  return (
    <Page wide>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-col gap-1">
          <H1 className="max-md:text-[22px]">{R.title}</H1>
          <p className="text-14 text-muted">{R.lead}</p>
        </div>
        <label className="flex items-center gap-2 text-14 font-semibold" data-testid="assessment-review-hide">
          <Switch checked={hidden} onCheckedChange={toggle} aria-label={R.hide} data-testid="assessment-review-hide-switch" />
          {R.hide}
        </label>
      </div>

      {groups.length === 0 ? (
        <p className="text-14 text-muted" data-testid="assessment-review-empty">
          {R.empty}
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-12">
          <div className="flex flex-col gap-4 md:col-span-8">
            {groups.map((g) => (
              <Panel key={g.type} className="flex flex-col gap-4" data-testid={`assessment-review-group-${g.type}`}>
                <PanelCap
                  title={<h2 className="m-0 font-mono text-16 leading-[1.3] font-semibold">{T.types[g.type] ?? g.type}</h2>}
                  aside={<Num className="text-12">{R.group(g.rows.length)}</Num>}
                />
                <div className="flex flex-col gap-4">
                  {g.rows.map((it) => (
                    <Task key={it.response_id} item={it} hidden={hidden} />
                  ))}
                </div>
              </Panel>
            ))}
          </div>
          <div className="flex flex-col gap-4 md:col-span-4">
            <Brush items={rows} />
            <Link to={`/me/assessment/attempts/${id}/result`} className={buttonVariants({ variant: "outline" })} data-testid="assessment-review-back">
              {R.back}
            </Link>
          </div>
        </div>
      )}
    </Page>
  );
}
