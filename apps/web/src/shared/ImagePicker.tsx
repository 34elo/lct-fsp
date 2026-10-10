import { useRef, useState } from "react";

import { Avatar, Button, cn } from "@fsp/ui";

import { ApiError } from "@/api/mutator";
import { cropSquare } from "@/shared/lib/image";

export interface ImagePickerText {
  upload: string;
  replace: string;
  remove: string;
  hint: string;
  error: (code?: string) => string;
}

/**
 * Загрузка картинки (аватар, логотип; E41-12): выбор файла, обрезка в квадрат на клиенте,
 * отправка и удаление. Формат и размер проверяет сервер. Без картинки — буквы на цвете.
 */
export function ImagePicker({
  name,
  src,
  text,
  onUpload,
  onRemove,
  size = 72,
  testId,
  className,
}: {
  name?: string | null;
  src?: string | null;
  text: ImagePickerText;
  onUpload: (file: File) => Promise<unknown>;
  onRemove: () => Promise<unknown>;
  size?: number;
  testId: string;
  className?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"put" | "del" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(file: File | undefined) {
    if (!file) return;
    setError(null);
    setBusy("put");
    try {
      await onUpload(await cropSquare(file));
    } catch (err) {
      setError(text.error(err instanceof ApiError ? err.code : undefined));
    } finally {
      setBusy(null);
      if (input.current) input.current.value = "";
    }
  }

  async function remove() {
    setError(null);
    setBusy("del");
    try {
      await onRemove();
    } catch {
      setError(text.error());
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-4", className)} data-testid={testId}>
      <Avatar name={name} src={src} size={size} />
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" loading={busy === "put"} onClick={() => input.current?.click()} data-testid={`${testId}-upload`}>
            {src ? text.replace : text.upload}
          </Button>
          {src && (
            <Button type="button" variant="ghost" loading={busy === "del"} onClick={() => void remove()} data-testid={`${testId}-remove`}>
              {text.remove}
            </Button>
          )}
        </div>
        <span className="text-13 text-muted">{text.hint}</span>
        {error && (
          <span role="alert" className="text-13 text-error" data-testid={`${testId}-error`}>
            {error}
          </span>
        )}
      </div>
      <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" tabIndex={-1} aria-hidden data-testid={`${testId}-input`} onChange={(e) => void upload(e.target.files?.[0])} />
    </div>
  );
}
