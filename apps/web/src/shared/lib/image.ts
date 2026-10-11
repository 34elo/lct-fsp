/** Максимальная сторона загружаемой картинки после обрезки. */
export const SQUARE_SIDE = 512;

/**
 * Обрезка картинки по центру до квадрата на стороне клиента. PNG и WebP остаются
 * в своём формате (прозрачность логотипа), остальное идёт JPEG. Нет canvas или файл не
 * читается — возвращаем исходный: проверку формата и размера всё равно делает сервер.
 */
export async function cropSquare(file: File, side = SQUARE_SIDE): Promise<File> {
  if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
  try {
    const bmp = await createImageBitmap(file);
    const min = Math.min(bmp.width, bmp.height);
    if (!min) return file;
    const out = Math.min(side, min);
    const canvas = document.createElement("canvas");
    canvas.width = out;
    canvas.height = out;
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bmp, (bmp.width - min) / 2, (bmp.height - min) / 2, min, min, 0, 0, out, out);
    bmp.close?.();
    const type = file.type === "image/png" || file.type === "image/webp" ? file.type : "image/jpeg";
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, type, 0.9));
    if (!blob || blob.type !== type) return file;
    const ext = type === "image/png" ? "png" : type === "image/webp" ? "webp" : "jpg";
    return new File([blob], `image.${ext}`, { type });
  } catch {
    return file;
  }
}
