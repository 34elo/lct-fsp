import { getProfilePdfCandidatesMeProfilePdfGetUrl } from "@/api/endpoints/candidates/candidates";
import { API_BASE } from "@/api/mutator";
import { getAccessToken } from "@/shared/lib/token";

/**
 * Скачивает PDF-профиль. Сгенерированный `profilePdf…Get` разбирает тело как JSON (мутатор orval),
 * поэтому для бинарного ответа берём только его URL из клиента и читаем `Blob` сами.
 * Возвращает false при ошибке.
 */
export async function downloadProfilePdf(name: string): Promise<boolean> {
  try {
    const token = getAccessToken();
    const r = await fetch(`${API_BASE}${getProfilePdfCandidatesMeProfilePdfGetUrl()}`, {
      credentials: "include",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!r.ok) return false;
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    return true;
  } catch {
    return false;
  }
}
