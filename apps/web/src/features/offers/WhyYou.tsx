import { MatchWhy, SectionLabel, type WhyItem } from "@fsp/ui";

import type { CompanyReliability, WhyYou as WhyYouDto } from "@/api/model";
import { INT_TEXT as T } from "./text";

/** «Почему вы»: топ факторов совпадения и то, что не подтверждено. Только данные самого кандидата. */
export function whyYouItems(why: WhyYouDto | null | undefined): WhyItem[] {
  if (!why) return [];
  return [
    ...(why.factors ?? []).map((f): WhyItem => ({ kind: "ok", text: f.text })),
    ...(why.unconfirmed ?? []).map((t): WhyItem => ({ kind: "warn", text: t })),
  ];
}

/** Рейтинг ответственности компании: доля ответов и средний срок. При малой выборке API отдаёт null. */
export function reliabilityText(r: CompanyReliability | null | undefined): string {
  if (!r || r.response_rate == null) return T.noReliability;
  const parts = [T.responseRate(Math.round(r.response_rate * 100))];
  if (r.avg_response_hours != null) parts.push(T.avgHours(r.avg_response_hours));
  return parts.join(", ");
}

export function WhyYouBlock({ why, reliability }: { why: WhyYouDto | null | undefined; reliability?: CompanyReliability | null }) {
  const items = whyYouItems(why);
  return (
    <div className="grid gap-3">
      <div className="grid gap-1.5">
        <SectionLabel>{T.why}</SectionLabel>
        {items.length > 0 ? <MatchWhy items={items} /> : <p className="text-13 text-muted">{T.whyNone}</p>}
      </div>
      <div className="grid gap-1">
        <SectionLabel>{T.reliability}</SectionLabel>
        <p className="text-13">{reliabilityText(reliability)}</p>
      </div>
    </div>
  );
}
