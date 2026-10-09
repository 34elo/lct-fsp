import { Button } from "@fsp/ui";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { authErrorText } from "@/features/auth/errors";
import { ErrorNote } from "@/features/auth/ui";
import { useAuth } from "@/shared/lib/auth";
import { JURY, juryEnabled } from "./jury";
import { T } from "./text";

type Who = "candidate" | "employer";

/** Кнопки «войти как жюри» и подсказка «что попробовать». Без `VITE_JURY_MODE` ничего не рисует.
 * Каждый браузер получает свою песочницу (E40-1): действия разных членов жюри не пересекаются. */
export function JuryEntry() {
  const { loginAsJury } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<Who | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!juryEnabled()) return null;

  async function enter(who: Who) {
    setBusy(who);
    setError(null);
    try {
      await loginAsJury(who);
      navigate(JURY[who].to);
    } catch (err) {
      setError(authErrorText(err, T.juryError));
      setBusy(null);
    }
  }

  return (
    <section aria-label={T.juryTitle} data-testid="jury-entry" className="flex flex-col gap-3 rounded-xl border border-hairline bg-card p-4">
      <h2 className="font-mono text-16 font-semibold">{T.juryTitle}</h2>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button variant="outline" loading={busy === "candidate"} disabled={busy !== null} onClick={() => enter("candidate")} data-testid="jury-candidate">
          {T.juryCandidate}
        </Button>
        <Button variant="outline" loading={busy === "employer"} disabled={busy !== null} onClick={() => enter("employer")} data-testid="jury-employer">
          {T.juryEmployer}
        </Button>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      <ul className="flex flex-col gap-1 text-13 text-muted">
        {T.juryTry.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </section>
  );
}
