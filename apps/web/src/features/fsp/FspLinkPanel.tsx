import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  fspStartAuthFspStartGet,
  getFspOverviewCandidatesMeFspGetQueryKey,
  useFspLinkCandidatesMeFspLinkPost,
  useFspOverviewCandidatesMeFspGet,
  useFspSyncCandidatesMeFspSyncPost,
  useFspVerifyCandidatesMeFspVerifyPost,
} from "@/api/endpoints/fsp/fsp";
import { ErrorNote, fieldClass } from "@/features/auth/ui";
import { fspApiError, fspErrorText } from "@/features/fsp/text";
import { Button } from "@/shared/ui/button";

type Mode = "idle" | "manual" | "code";

/**
 * Привязка ФСП: OAuth «Войти через ФСП» (самая заметная кнопка), запасной путь — ID/email с кодом
 * или ручной ID. `next` — куда ФСП вернёт в SPA. Результат возврата читаем из `?fsp=`.
 */
export function FspLinkPanel({ next, onLinked }: { next: string; onLinked?: () => void }) {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const overview = useFspOverviewCandidatesMeFspGet();
  const link = useFspLinkCandidatesMeFspLinkPost();
  const verify = useFspVerifyCandidatesMeFspVerifyPost();
  const sync = useFspSyncCandidatesMeFspSyncPost();

  const [mode, setMode] = useState<Mode>("idle");
  const [ident, setIdent] = useState("");
  const [code, setCode] = useState("");
  const [masked, setMasked] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);

  const back = params.get("fsp");
  const backError = back === "error" ? fspErrorText(params.get("reason")) : null;
  const backLinked = back === "linked";

  const refresh = () => qc.invalidateQueries({ queryKey: getFspOverviewCandidatesMeFspGetQueryKey() });

  async function oauth() {
    setError(null);
    setRedirecting(true);
    try {
      const res = await fspStartAuthFspStartGet({ next });
      const url = (res.data as { url?: string } | void)?.url;
      if (!url) throw new Error("no url");
      window.location.assign(url);
    } catch (e) {
      setRedirecting(false);
      setError(fspApiError(e));
    }
  }

  async function submitIdent(manual: boolean) {
    const v = ident.trim();
    if (!v) return;
    setError(null);
    const body = v.includes("@") ? { email: v, manual } : { participant_id: v, manual };
    try {
      const res = await link.mutateAsync({ data: body });
      const out = res.data as { method?: string; masked_contact?: string | null };
      if (out.method === "code") {
        setMasked(out.masked_contact ?? null);
        setMode("code");
      } else {
        setInfo("ID сохранён без подтверждения: достижения подтянем, но доверие к ним ниже.");
        setMode("idle");
        await refresh();
        onLinked?.();
      }
    } catch (e) {
      setError(fspApiError(e));
    }
  }

  async function submitCode() {
    setError(null);
    try {
      await verify.mutateAsync({ data: { code: code.trim() } });
      setInfo("Профиль ФСП подтверждён. Загружаем достижения…");
      setMode("idle");
      setCode("");
      await refresh();
      onLinked?.();
    } catch (e) {
      setError(fspApiError(e));
    }
  }

  async function runSync() {
    setError(null);
    try {
      await sync.mutateAsync();
      setInfo("Обновляем данные из ФСП…");
    } catch (e) {
      setError(fspApiError(e));
    }
  }

  const ov = overview.data?.status === 200 ? overview.data.data : undefined;
  const linked = ov?.link.linked ?? false;
  const verified = ov?.link.verified ?? false;
  const teams = ov?.teams ?? [];

  const notes = (
    <>
      {(backError || error) && <ErrorNote>{error ?? backError}</ErrorNote>}
      {!error && backLinked && !linked && (
        <p role="status" className="text-sm text-brand-fg">ФСП подключена, подтягиваем данные…</p>
      )}
      {info && (
        <p role="status" className="text-sm text-brand-fg">
          {info}
        </p>
      )}
    </>
  );

  function dismissBack() {
    if (back) {
      const p = new URLSearchParams(params);
      p.delete("fsp");
      p.delete("reason");
      setParams(p, { replace: true });
    }
  }

  if (overview.isPending) return <p role="status" className="text-sm text-muted">Проверяем привязку ФСП…</p>;

  if (linked) {
    return (
      <div className="flex flex-col gap-2" onClickCapture={dismissBack}>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-semibold">{verified ? "ФСП подтверждена" : "ФСП привязана без подтверждения"}</span>
          {ov?.link.participant_id && (
            <span className="font-mono text-xs text-muted">{ov.link.participant_id}</span>
          )}
          {teams.length > 0 && <span className="text-xs text-muted">команды: {teams.map((t) => t.name).join(", ")}</span>}
        </p>
        {notes}
        <Button variant="outline" size="sm" className="self-start" onClick={() => void runSync()} disabled={sync.isPending}>
          Обновить из ФСП
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {notes}
      <Button size="lg" onClick={() => void oauth()} disabled={redirecting}>
        {redirecting ? "Переходим в ФСП…" : "Войти через ФСП"}
      </Button>
      <p className="text-[13px] text-muted">Откроется страница ФСП. Мы получим только ваши результаты и разряды.</p>

      {mode === "idle" && (
        <button type="button" className="self-start text-sm text-brand-fg underline" onClick={() => setMode("manual")}>
          Ввести ID участника или email
        </button>
      )}

      {mode === "manual" && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void submitIdent(false);
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            ID участника или email в ФСП
            <input className={fieldClass} value={ident} onChange={(e) => setIdent(e.target.value)} placeholder="p-anya" autoComplete="off" />
          </label>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={!ident.trim() || link.isPending}>
              Получить код
            </Button>
            <Button type="button" size="sm" variant="ghost" disabled={!ident.trim() || link.isPending} onClick={() => void submitIdent(true)}>
              Привязать без кода
            </Button>
          </div>
          <p className="text-xs text-muted">Без кода достижения тоже подтянутся, но подтверждённой привязка не считается.</p>
        </form>
      )}

      {mode === "code" && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void submitCode();
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            Код из сообщения{masked ? ` (отправили на ${masked})` : ""}
            <input
              className={fieldClass}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </label>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={!code.trim() || verify.isPending}>
              Подтвердить
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setMode("manual")}>
              Назад
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
