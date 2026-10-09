import { API_BASE } from "@/api/mutator";

/** `avatar_url` из API (`/users/{id}/avatar?v=`) → адрес для `<img>` за gateway (E39-24). */
export function avatarSrc(url: string | null | undefined): string | null {
  return url ? `${API_BASE}${url}` : null;
}
