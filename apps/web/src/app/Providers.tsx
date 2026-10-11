import { Toaster } from "@fsp/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { AuthProvider } from "@/shared/lib/auth";
import { ThemeProvider } from "@/shared/lib/theme";
import { EventStreamProvider } from "@/shared/lib/useEventStream";

export function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });
}

/** QueryClient → Theme → Auth → SSE. Роутер снаружи. */
export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  const [qc] = useState(() => client ?? makeQueryClient());
  return (
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <AuthProvider>
          <EventStreamProvider>{children}</EventStreamProvider>
          <Toaster position="bottom-center" />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
