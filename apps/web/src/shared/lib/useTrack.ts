import { useCallback } from "react";

import { getTracker, type TrackProps } from "@/shared/lib/track";

/**
 * Трекер событий интерфейса: `const track = useTrack(); track("chip_removed", { key, source })`.
 * В `props` только числа, флаги и slug-и из трекинг-плана (metrics.md §2.3): ПДн и свободный текст нельзя.
 */
export function useTrack() {
  return useCallback((event: string, props?: TrackProps) => getTracker().track(event, props), []);
}
