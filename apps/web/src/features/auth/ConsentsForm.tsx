import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";

import { getGetConsentsMeConsentsGetQueryKey, useGetConsentsMeConsentsGet, usePutConsentsMeConsentsPut } from "@/api/endpoints/consents/consents";
import type { ConsentOut } from "@/api/model";
import { ApiError } from "@/api/mutator";
import { ErrorNote } from "@/features/auth/ui";
import { Button } from "@/shared/ui/button";

/** Тексты по типам согласий (design/screens/M1_Onboarding, security.md §2). */
const COPY: Record<string, { title: string; hint: string }> = {
  pd_processing: { title: "Обработка персональных данных", hint: "Имя, контакты и резюме нужны, чтобы создать профиль." },
  fsp_data: { title: "Данные ФСП", hint: "Результаты соревнований подтверждают ваши навыки." },
  code_analysis: { title: "Анализ кода", hint: "Читаем ваши публичные репозитории, чтобы подтвердить навыки. Код не запускается." },
  telegram_notifications: { title: "Уведомления в Telegram", hint: "Офферы и новые результаты ФСП." },
  public_profile: { title: "Публичная карточка", hint: "Страница профиля, которую можно показать по ссылке." },
};

export function ConsentsForm({ onDone, submitLabel = "Продолжить" }: { onDone: () => void | Promise<void>; submitLabel?: string }) {
  const qc = useQueryClient();
  const list = useGetConsentsMeConsentsGet();
  const save = usePutConsentsMeConsentsPut();
  const items = list.data?.data as ConsentOut[] | undefined;
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  // Начальное состояние — то, что уже выдано (обязательные и выданные видны отмеченными).
  useEffect(() => {
    if (items) setChecked(Object.fromEntries(items.map((c) => [c.type, c.granted])));
  }, [items]);

  if (list.isPending) return <p role="status" className="text-sm text-muted">Загрузка…</p>;
  if (!items) return <ErrorNote>Не удалось загрузить согласия. Обновите страницу.</ErrorNote>;

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
        setError("Текст согласия обновился. Перечитайте и подтвердите ещё раз.");
        await qc.invalidateQueries({ queryKey: getGetConsentsMeConsentsGetQueryKey() });
      } else {
        setError("Не удалось сохранить согласия, попробуйте позже");
      }
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2">
        {items.map((c) => {
          const copy = COPY[c.type] ?? { title: c.type, hint: "" };
          return (
            <li key={c.type}>
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-hairline bg-card p-3 has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand">
                <input
                  type="checkbox"
                  className="mt-1 size-5 shrink-0 accent-brand"
                  checked={!!checked[c.type]}
                  onChange={(e) => setChecked((s) => ({ ...s, [c.type]: e.target.checked }))}
                />
                <span className="flex flex-col gap-0.5">
                  <span className="font-semibold">
                    {copy.title}{" "}
                    <span className={c.required ? "text-xs font-normal text-signal" : "text-xs font-normal text-muted"}>
                      {c.required ? "обязательно" : "по желанию"}
                    </span>
                  </span>
                  <span className="text-sm text-muted">{copy.hint}</span>
                </span>
              </label>
            </li>
          );
        })}
      </ul>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button type="submit" disabled={missingRequired || save.isPending}>
        {save.isPending ? "Сохраняем…" : submitLabel}
      </Button>
      {missingRequired && <p className="text-xs text-muted">Без обязательных согласий создать профиль нельзя.</p>}
    </form>
  );
}
