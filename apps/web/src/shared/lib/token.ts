/** Access-токен живёт только в памяти. */
let accessToken: string | null = null;
const listeners = new Set<() => void>();

export const getAccessToken = () => accessToken;

export function setAccessToken(t: string | null) {
  accessToken = t;
  listeners.forEach((l) => l());
}
