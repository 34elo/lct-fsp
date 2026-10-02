import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { refreshAccess } from "@/api/mutator";
import { getMe } from "@/api/endpoints/account/account";
import { login as loginRequest, logout as logoutRequest } from "@/api/endpoints/auth/auth";
import type { Me } from "@/api/model";
import { setAccessToken } from "@/shared/lib/token";

export type Role = "candidate" | "employer" | "fsp_admin";

type AuthState =
  | { status: "loading"; me: null }
  | { status: "anonymous"; me: null }
  | { status: "authenticated"; me: Me };

interface AuthApi {
  status: AuthState["status"];
  me: Me | null;
  role: Role | null;
  login(email: string, password: string): Promise<void>;
  logout(): Promise<void>;
}

const Ctx = createContext<AuthApi | null>(null);

/** Куда вести пользователя после входа и на что у него есть права. */
export const HOME_BY_ROLE: Record<Role, string> = {
  candidate: "/me",
  employer: "/employer/search",
  fsp_admin: "/federation",
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", me: null });

  // Тихий refresh при старте: access в памяти, refresh-cookie даёт новый.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (await refreshAccess()) {
          const res = await getMe();
          if (alive) return setState({ status: "authenticated", me: res.data });
        }
      } catch {
        /* считаем анонимом */
      }
      if (alive) setState({ status: "anonymous", me: null });
    })();
    return () => {
      alive = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginRequest({ email, password });
    setAccessToken(res.data.access_token);
    const me = await getMe();
    setState({ status: "authenticated", me: me.data });
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      setAccessToken(null);
      qc.clear();
      setState({ status: "anonymous", me: null });
    }
  }, [qc]);

  const value = useMemo<AuthApi>(
    () => ({ status: state.status, me: state.me, role: state.me?.role ?? null, login, logout }),
    [state, login, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth вне AuthProvider");
  return v;
}
