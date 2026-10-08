import { useState } from "react";

import { Button } from "@fsp/ui";
import { useSubmitSusRunTokenSusPost } from "@/api/endpoints/live-runs/live-runs";
import { ErrorNote } from "@/features/auth/ui";
import { runError, SUS_ITEMS, T } from "@/features/runs/text";

type Agree = "yes" | "no" | "none";

const AGREE: [Agree, string][] = [
  ["yes", T.agreeYes],
  ["no", T.agreeNo],
  ["none", T.agreeNone],
];

/** Анкета SUS: 10 утверждений по шкале 1–5, согласие с категорией, заметка. Отправка завершает прогон. */
export function SusForm({ token, onDone }: { token: string; onDone: () => void }) {
  const submit = useSubmitSusRunTokenSusPost();
  const [answers, setAnswers] = useState<(number | null)[]>(() => SUS_ITEMS.map(() => null));
  const [agree, setAgree] = useState<Agree>("none");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (answers.some((a) => a === null)) {
      setError(T.incomplete);
      return;
    }
    setError(null);
    try {
      await submit.mutateAsync({
        token,
        data: {
          answers: answers as number[],
          category_agree: agree === "none" ? null : agree === "yes",
          notes: notes.trim() || null,
        },
      });
      onDone();
    } catch (e) {
      setError(runError(e));
    }
  }

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <header className="flex flex-col gap-1">
        <h2 className="text-xl font-bold">{T.susTitle}</h2>
        <p className="text-sm text-muted">{T.susLead}</p>
      </header>

      {SUS_ITEMS.map((text, i) => (
        <fieldset key={text} className="flex flex-col gap-2">
          <legend className="text-sm font-medium">
            {i + 1}. {text}
          </legend>
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4, 5].map((v) => (
              <label
                key={v}
                className={`flex h-11 flex-1 cursor-pointer items-center justify-center rounded-lg border text-sm font-semibold ${
                  answers[i] === v ? "border-ink bg-ink text-card" : "border-hairline bg-card text-ink"
                }`}
              >
                <input
                  type="radio"
                  name={`sus-${i}`}
                  value={v}
                  className="sr-only"
                  checked={answers[i] === v}
                  onChange={() => setAnswers((a) => a.map((x, j) => (j === i ? v : x)))}
                  aria-label={`${i + 1}: ${v}`}
                />
                {v}
              </label>
            ))}
          </div>
          <div className="flex justify-between text-xs text-muted">
            <span>{T.scaleMin}</span>
            <span>{T.scaleMax}</span>
          </div>
        </fieldset>
      ))}

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">{T.agreeTitle}</legend>
        <div className="flex flex-wrap gap-2">
          {AGREE.map(([v, label]) => (
            <label
              key={v}
              className={`flex h-11 cursor-pointer items-center rounded-lg border px-4 text-sm ${
                agree === v ? "border-ink bg-ink text-card" : "border-hairline bg-card text-ink"
              }`}
            >
              <input type="radio" name="agree" className="sr-only" checked={agree === v} onChange={() => setAgree(v)} />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex flex-col gap-1 text-sm font-medium">
        {T.notes}
        <textarea
          value={notes}
          maxLength={500}
          rows={3}
          onChange={(e) => setNotes(e.target.value)}
          className="w-full rounded-lg border border-hairline bg-card p-3 font-normal text-ink"
        />
      </label>

      {error && <ErrorNote>{error}</ErrorNote>}
      <Button type="submit" disabled={submit.isPending}>
        {submit.isPending ? T.sending : T.send}
      </Button>
    </form>
  );
}
