/** Access-токен живёт только в памяти (frontend.md §3). */
let accessToken: string | null = null;
const listeners = new Set<() => void>();

export const getAccessToken = () => accessToken;

export function setAccessToken(t: string | null) {
  accessToken = t;
  listeners.forEach((l) => l());
}

export function subscribeToken(l: () => void) {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
