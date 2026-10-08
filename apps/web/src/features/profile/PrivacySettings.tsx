import { Panel, PanelCap, Switch } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  getGetProfileCandidatesMeProfileGetQueryKey,
  usePatchVisibilityCandidatesMeVisibilityPatch,
} from "@/api/endpoints/candidates/candidates";
import type { Visibility } from "@/api/model";
import { privacyText as P } from "@/features/profile/text";

type Key = (typeof P.items)[number]["key"];

/** Строка настройки `.rw`: название с пояснением слева, переключатель справа. */
export function SettingRow({
  id,
  label,
  hint,
  checked,
  disabled,
  onChange,
  testId,
}: {
  id: string;
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange?: (value: boolean) => void;
  testId?: string;
}) {
  return (
    <div className="flex min-h-11 items-center gap-3 border-t border-hairline py-2.5 first:border-t-0 first:pt-0">
      <label htmlFor={id} className="flex min-w-0 flex-1 flex-col">
        <span className="font-medium">{label}</span>
        {hint && <span className="text-13 text-muted">{hint}</span>}
      </label>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onChange} data-testid={testId} />
    </div>
  );
}

/** Что видят компании: каждый переключатель сразу сохраняется (`PATCH /candidates/me/visibility`). */
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
    <Panel data-testid="privacy-settings" aria-label={P.title}>
      <PanelCap title={P.title} />
      <p className="mb-2 text-13 text-muted">{P.hint}</p>
      {P.items.map((it) => (
        <SettingRow
          key={it.key}
          id={`privacy-${it.key}`}
          label={it.label}
          hint={it.hint}
          checked={Boolean(visibility[it.key])}
          disabled={patch.isPending}
          onChange={(v) => void toggle(it.key, v)}
          testId={`privacy-${it.key}`}
        />
      ))}
      {error && (
        <p role="alert" className="mt-2 rounded-lg bg-tint-50 px-3 py-2 text-13" data-testid="privacy-error">
          {P.saveError}
        </p>
      )}
    </Panel>
  );
}
