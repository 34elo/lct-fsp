import { Card } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getGetProfileCandidatesMeProfileGetQueryKey,
  usePatchVisibilityCandidatesMeVisibilityPatch,
} from "@/api/endpoints/candidates/candidates";
import type { Visibility } from "@/api/model";
import { privacyText as P } from "@/features/profile/text";

type Key = (typeof P.items)[number]["key"];

/** Переключатели видимости для работодателя; каждый сразу сохраняется (`PATCH /candidates/me/visibility`). */
export function PrivacySettings({ visibility }: { visibility: Visibility }) {
  const qc = useQueryClient();
  const patch = usePatchVisibilityCandidatesMeVisibilityPatch();
  const [error, setError] = useState(false);

  async function toggle(key: Key, value: boolean) {
    setError(false);
    try {
      const res = await patch.mutateAsync({ data: { [key]: value } });
      if (res.status !== 200) throw new Error("visibility");
      await qc.invalidateQueries({ queryKey: getGetProfileCandidatesMeProfileGetQueryKey() });
    } catch {
      setError(true);
    }
  }

  return (
    <Card className="flex flex-col gap-3 p-5" data-testid="privacy-settings">
      <h2 className="font-mono text-17 font-semibold">{P.title}</h2>
      <p className="text-13 text-muted">{P.hint}</p>
      {P.items.map((it) => (
        <label key={it.key} className="flex min-h-11 items-start gap-3 text-14">
          <input
            type="checkbox"
            role="switch"
            className="mt-1 size-5"
            checked={Boolean(visibility[it.key])}
            disabled={patch.isPending}
            onChange={(e) => void toggle(it.key, e.target.checked)}
            data-testid={`privacy-${it.key}`}
          />
          <span className="flex flex-col">
            <span className="font-semibold">{it.label}</span>
            <span className="text-13 text-muted">{it.hint}</span>
          </span>
        </label>
      ))}
      {error && (
        <p role="alert" className="rounded-lg bg-tint-50 px-3 py-2 text-13" data-testid="privacy-error">
          {P.saveError}
        </p>
      )}
    </Card>
  );
}
