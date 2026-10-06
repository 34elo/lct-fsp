import type { CandidateProfile } from "@/api/model";
import { API_BASE } from "@/api/mutator";
import { getAccessToken } from "@/shared/lib/token";

/**
 * Тонкий адаптер: бэкенд уже отдаёт `claimed_vs_confirmed` и `/candidates/me/profile.pdf`,
 * но в сгенерированном клиенте их пока нет (openapi.json устарел, `make api-gen` не запускался).
 * После перегенерации тип и скачивание берутся из `@/api`, адаптер удаляется.
 */
export interface ClaimedRow {
  profession: string;
  declared_grade?: string | null;
  resume_grade?: string | null;
  confirmed_grade?: string | null;
  status: "confirmed" | "overclaimed" | "underclaimed" | "unconfirmed";
}

export const claimedOf = (p: CandidateProfile): ClaimedRow[] =>
  (p as CandidateProfile & { claimed_vs_confirmed?: ClaimedRow[] }).claimed_vs_confirmed ?? [];

/** Скачивает PDF-профиль с Bearer-токеном. Возвращает false при ошибке. */
export async function downloadProfilePdf(name: string): Promise<boolean> {
  try {
    const token = getAccessToken();
    const r = await fetch(`${API_BASE}/candidates/me/profile.pdf`, {
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
