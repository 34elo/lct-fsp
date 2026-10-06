import { BuildLog, Button, type LogLine } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import {
  useConfirmResumeCandidatesMeResumesResumeIdConfirmPost,
  useUploadResumeCandidatesMeResumesPost,
} from "@/api/endpoints/resumes/resumes";
import { getGetProfileCandidatesMeProfileGetQueryKey } from "@/api/endpoints/candidates/candidates";
import type { ParsedResumeEdits } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { failureText, RESUME_HINT, summaryLines } from "@/features/onboarding/text";
import { Understood } from "@/features/onboarding/Understood";
import { stageLines, useResumeJob } from "@/features/onboarding/useResumeJob";
import { Note } from "@/features/onboarding/Note";

const MAX_BYTES = 10 * 1024 * 1024;

function uploadError(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code ?? String(e.status)) {
      case "file_too_large":
      case "413":
        return "Файл больше 10 МБ.";
      case "unsupported_file_type":
      case "415":
        return "Подходят только PDF и DOCX.";
      case "empty_file":
        return "Файл пустой.";
      case "consent_required":
        return "Нужно согласие на обработку персональных данных.";
      case "429":
        return "Сегодня загружено слишком много резюме. Попробуйте завтра.";
    }
  }
  return "Не удалось загрузить файл, попробуйте позже.";
}

function confirmError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "unknown_skill") {
      const errs = (e.body as { errors?: { message?: string }[] } | undefined)?.errors ?? [];
      const names = errs.map((x) => x.message).filter(Boolean).join(", ");
      return `Этих навыков нет в справочнике: ${names || "добавленные вами"}. Уберите их или выберите другой вариант.`;
    }
    if (e.code === "resume_not_parsed") return "Разбор ещё не закончен, подождите немного.";
  }
  return "Не удалось сохранить, попробуйте ещё раз.";
}

/** Шаг «Резюме»: загрузка → лог сборки → «вот что я понял» → подтверждение. */
export function ResumeStep({ onDone, onSkip }: { onDone: (skills: number) => void; onSkip: () => void }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [ids, setIds] = useState<{ resumeId: string; jobId: string } | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmErr, setConfirmErr] = useState<string | null>(null);

  const upload = useUploadResumeCandidatesMeResumesPost();
  const confirm = useConfirmResumeCandidatesMeResumesResumeIdConfirmPost();
  const job = useResumeJob(ids?.resumeId ?? null, ids?.jobId ?? null);
  const status = job.resume?.status;

  async function pick(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (file.size > MAX_BYTES) return setError("Файл больше 10 МБ.");
    if (!/\.(pdf|docx)$/i.test(file.name)) return setError("Подходят только PDF и DOCX.");
    try {
      const res = await upload.mutateAsync({ data: { file } });
      const body = res.data as { resume_id: string; job_id: string };
      setFileName(file.name);
      job.reset();
      setIds({ resumeId: body.resume_id, jobId: body.job_id });
    } catch (e) {
      setError(uploadError(e));
    }
  }

  async function submit(edits: ParsedResumeEdits) {
    if (!ids) return;
    setConfirmErr(null);
    try {
      await confirm.mutateAsync({ resumeId: ids.resumeId, data: { edits } });
      await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
      const parsed = job.resume?.parsed;
      const kept = (parsed?.skills ?? []).filter((s) => !s.slug || !(edits.remove_skills ?? []).includes(s.slug));
      onDone(kept.length + (edits.add_skills?.length ?? 0) + (parsed?.unknown_skills?.length ?? 0));
    } catch (e) {
      setConfirmErr(confirmError(e));
    }
  }

  const picker = (
    <div className="flex flex-col gap-3">
      <p className="text-14 text-muted">{RESUME_HINT}</p>
      <input
        ref={input}
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        aria-label="Файл резюме"
        className="hidden"
        onChange={(e) => {
          void pick(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <Button size="lg" data-testid="onboarding-resume-pick" onClick={() => input.current?.click()} loading={upload.isPending}>
        {upload.isPending ? "Загружаем…" : "Выбрать файл"}
      </Button>
      {error && <Note>{error}</Note>}
      <Button variant="ghost" data-testid="onboarding-skip" onClick={onSkip}>
        Пропустить, заполню вручную
      </Button>
    </div>
  );

  if (!ids) return picker;

  if (status === "failed") {
    return (
      <div className="flex flex-col gap-3">
        <BuildLog title="разбор резюме" lines={[...stageLines(job.stages, status), { id: "fail", text: "Разбор не удался", state: "fail" }]} />
        <Note>{failureText(job.resume?.error)}</Note>
        {picker}
      </div>
    );
  }

  if ((status === "parsed" || status === "confirmed") && job.resume?.parsed) {
    const parsed = job.resume.parsed;
    const lines: LogLine[] = [
      ...stageLines(job.stages, status),
      ...summaryLines(parsed).map((t, i) => ({ id: `s${i}`, text: t, state: "done" as const })),
    ];
    return (
      <div className="flex flex-col gap-4">
        <BuildLog title={`разбор резюме${fileName ? ` · ${fileName}` : ""}`} lines={lines} />
        <Understood parsed={parsed} onConfirm={(e) => void submit(e)} pending={confirm.isPending} error={confirmErr} onSkip={onSkip} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <BuildLog title={`разбор резюме${fileName ? ` · ${fileName}` : ""}`} lines={stageLines(job.stages, status)} />
      {job.isError && <Note>Не удаётся узнать состояние разбора. Обновите страницу.</Note>}
      <Button variant="ghost" data-testid="onboarding-skip" onClick={onSkip}>
        Пропустить, заполню вручную
      </Button>
    </div>
  );
}
