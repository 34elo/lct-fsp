import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getGetResumeCandidatesMeResumesResumeIdGetQueryKey,
  useGetResumeCandidatesMeResumesResumeIdGet,
} from "@/api/endpoints/resumes/resumes";
import type { ResumeOut } from "@/api/model";
import type { LogLine } from "@/features/onboarding/BuildLog";
import { useEventStream } from "@/shared/lib/useEventStream";

interface Progress {
  stage: string;
  pct: number;
  message: string;
}

/**
 * Состояние разбора резюме: SSE `job.progress` даёт этапы для лога, `resume.parsed|failed` будят запрос,
 * опрос раз в 3 с страхует от пропущенного события (поток мог переподключаться).
 */
export function useResumeJob(resumeId: string | null, jobId: string | null) {
  const qc = useQueryClient();
  const [stages, setStages] = useState<Progress[]>([]);

  const q = useGetResumeCandidatesMeResumesResumeIdGet(resumeId ?? "", {
    query: {
      enabled: !!resumeId,
      refetchInterval: (query) => {
        const s = (query.state.data?.data as ResumeOut | undefined)?.status;
        return s === "queued" || s === "parsing" || s === undefined ? 3000 : false;
      },
    },
  });

  useEventStream((m) => {
    if (!resumeId) return;
    const d = m.data as { job_id?: string; resume_id?: string } & Partial<Progress>;
    if (m.type === "job.progress") {
      if (d.job_id !== resumeId && d.job_id !== jobId) return;
      const p = { stage: d.stage ?? "", pct: d.pct ?? 0, message: d.message ?? "" };
      setStages((s) => (s.some((x) => x.stage === p.stage) ? s.map((x) => (x.stage === p.stage ? p : x)) : [...s, p]));
    } else if (d.resume_id === resumeId) {
      void qc.invalidateQueries({ queryKey: getGetResumeCandidatesMeResumesResumeIdGetQueryKey(resumeId) });
    }
  }, ["job.progress", "resume.parsed", "resume.failed"]);

  const resume = q.data?.data as ResumeOut | undefined;
  return { resume, stages, isError: q.isError, reset: () => setStages([]) };
}

/** Строки лога: пройденные этапы — готово, последний — в работе (пока разбор не закончен). */
export function stageLines(stages: Progress[], status: ResumeOut["status"] | undefined): LogLine[] {
  const finished = status === "parsed" || status === "confirmed";
  const failed = status === "failed";
  const real = stages.filter((s) => s.stage !== "done");
  const lines: LogLine[] = real.map((s, i) => ({
    id: s.stage,
    text: s.message || s.stage,
    state: failed && i === real.length - 1 ? "fail" : finished || i < real.length - 1 ? "done" : "active",
  }));
  if (lines.length === 0 && !finished && !failed) {
    lines.push({ id: "queued", text: "Ждём очереди разбора…", state: "active" });
  }
  return lines;
}
