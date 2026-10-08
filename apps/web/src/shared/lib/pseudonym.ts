import { pseudonymLabel } from "@fsp/ui";

/**
 * Псевдоним для показа: «Candidate #4821» (роль при создании кандидата неизвестна) → «Backend #4821».
 * Уже осмысленный псевдоним возвращается как есть.
 */
export function displayPseudonym(pseudonym: string, role?: string | null): string {
  const m = /^Candidate #(\S+)$/.exec(pseudonym);
  return m ? pseudonymLabel(role, m[1]!) : pseudonym;
}
