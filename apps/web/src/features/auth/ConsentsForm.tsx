import { Button, Checkbox, ErrorState, Label, Skeleton, cn } from "@fsp/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { getGetConsentsMeConsentsGetQueryKey, useGetConsentsMeConsentsGet, usePutConsentsMeConsentsPut } from "@/api/endpoints/consents/consents";
import type { ConsentOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { authText } from "@/features/auth/text";
import { ErrorNote } from "@/features/auth/ui";

const t = authText.consents;
/** E41-3: анализ кода в разработке — согласие не показываем. */
export const HIDDEN_CONSENTS = new Set(["code_analysis"]);

/**
 * Согласия при входе (E39-6): по умолчанию только обязательные; необязательные выдаются в настройках
 * и до этого выключены. `requiredOnly={false}` — полный список.
 */
export function ConsentsForm({
  onDone,
  submitLabel = t.submit,
  requiredOnly = true,
}: {
  onDone: () => void | Promise<void>;
  submitLabel?: string;
  requiredOnly?: boolean;
}) {
  const qc = useQueryClient();
  const list = useGetConsentsMeConsentsGet();
  const save = usePutConsentsMeConsentsPut();
  const all = list.data?.data as ConsentOut[] | undefined;
  const items = useMemo(
    () => all && all.filter((c) => !HIDDEN_CONSENTS.has(c.type) && (!requiredOnly || c.required)),
    [all, requiredOnly],
  );
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  // Начальное состояние — то, что уже выдано (обязательные и выданные видны отмеченными).
  useEffect(() => {
    if (items) setChecked(Object.fromEntries(items.map((c) => [c.type, c.granted])));
  }, [items]);

  if (list.isPending)
    return (
      <div className="flex flex-col gap-2" data-testid="consents-form-loading">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
    );
  if (!items)
    return (
      <ErrorState
        title={t.loadError}
        description={t.loadErrorHint}
        onRetry={() => void list.refetch()}
        className="py-6"
      />
    );

  const missingRequired = items.some((c) => c.required && !checked[c.type]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!items || missingRequired) return;
    setError(null);
    try {
      await save.mutateAsync({
        data: { consents: items.map((c) => ({ type: c.type, granted: !!checked[c.type], version: c.current_version })) },
      });
      await qc.invalidateQueries({ queryKey: getGetConsentsMeConsentsGetQueryKey() });
      await onDone();
    } catch (err) {
      if (err instanceof ApiError && err.code === "consent_version_mismatch") {
        setError(t.versionMismatch);
        await qc.invalidateQueries({ queryKey: getGetConsentsMeConsentsGetQueryKey() });
      } else {
        setError(t.saveError);
      }
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3" data-testid="consents-form">
      <ul className="flex flex-col gap-2">
        {items.map((c) => {
          const copy = t.types[c.type] ?? { title: c.type, hint: "" };
          return (
            <li key={c.type}>
              <Label
                htmlFor={`consent-${c.type}`}
                data-testid={`consents-item-${c.type}`}
                className={cn(
                  "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border p-3",
                  checked[c.type] ? "border-brand bg-tint-50" : "border-hairline bg-card",
                )}
              >
                <Checkbox
                  id={`consent-${c.type}`}
                  className="mt-0.5"
                  checked={!!checked[c.type]}
                  onCheckedChange={(v) => setChecked((s) => ({ ...s, [c.type]: v === true }))}
                />
                <span className="flex flex-col gap-0.5">
                  <span className="font-semibold">
                    {copy.title}{" "}
                    <span className={cn("text-12 font-normal", c.required ? "text-brand-fg" : "text-muted")}>
                      {c.required ? t.required : t.optional}
                    </span>
                  </span>
                  <span className="text-14 font-normal text-muted">{copy.hint}</span>
                </span>
              </Label>
            </li>
          );
        })}
      </ul>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button type="submit" size="lg" disabled={missingRequired} loading={save.isPending} data-testid="consents-submit">
        {save.isPending ? t.saving : submitLabel}
      </Button>
      {missingRequired && <p className="text-12 text-muted">{t.missingRequired}</p>}
    </form>
  );
}
