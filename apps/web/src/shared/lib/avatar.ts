import { API_BASE } from "@/api/mutator";

/** `avatar_url` из API (`/users/{id}/avatar?v=`) → адрес для `<img>` за gateway. */
export function avatarSrc(url: string | null | undefined): string | null {
  return url ? `${API_BASE}${url}` : null;
}
