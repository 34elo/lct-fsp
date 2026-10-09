import { cn, Panel, StatusTag } from "@fsp/ui";

import { useGetStatsPublicStatsGet } from "@/api/endpoints/public/public";
import type { PublicStatsOut } from "@/api/model";
import { CountUp, Reveal } from "./motion";
import { hoverLift, SecLabel, SecTitle, sectionY, Wrap } from "./parts";
import { NUM_LABEL, T } from "./text";

const KEYS = ["candidates", "companies", "invitations", "median_days_to_invite"] as const;

/** Цифры платформы из `GET /public/stats`. Нет ответа или нет ни одной цифры: блок скрыт целиком; нет одной — скрыт её счётчик. */
export function Numbers() {
  const stats = useGetStatsPublicStatsGet({ query: { retry: false, staleTime: 5 * 60_000, refetchOnWindowFocus: false } });
  const data: PublicStatsOut | null = stats.data?.status === 200 ? stats.data.data : null;
  const items = KEYS.flatMap((k) => {
    const v = data?.[k];
    return typeof v === "number" ? [{ key: k, value: v }] : [];
  });
  if (items.length === 0) return null;
  return (
    <section id="nums" tabIndex={-1} className={cn("bg-tint-50 outline-none dark:bg-card", sectionY)}>
      <Wrap>
        <Reveal className="mb-7 flex flex-col gap-1.5 min-[861px]:mb-10">
          <SecLabel>{T.numsLabel}</SecLabel>
          <SecTitle>
            {T.numsTitle} <StatusTag state="claimed" className="ml-2 align-middle">{T.numsDemo}</StatusTag>
          </SecTitle>
        </Reveal>
        <div className="grid grid-cols-2 gap-3 min-[861px]:grid-cols-4 min-[861px]:gap-5">
          {items.map((it, i) => (
            <Reveal key={it.key} delay={i * 80} className="min-w-0">
              <Panel className={cn("flex h-full flex-col gap-2 p-[18px] min-[861px]:p-7", hoverLift)}>
                <CountUp value={it.value} className="font-mono text-[34px] leading-none font-bold tracking-[-0.02em] tabular-nums min-[861px]:text-[52px]" />
                <span className="text-[15px] text-muted">{NUM_LABEL[it.key](it.value)}</span>
              </Panel>
            </Reveal>
          ))}
        </div>
      </Wrap>
    </section>
  );
}
