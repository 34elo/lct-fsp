import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { refreshAccess } from "@/api/mutator";
import {
  authMagicAuthMagicPost,
  loginAuthLoginPost,
  logoutAuthLogoutPost,
  meMeGet,
  registerAuthRegisterPost,
} from "@/api/endpoints/auth/auth";
import type { AuthOut, MeOut } from "@/api/model";
import { setAccessToken } from "@/shared/lib/token";

export type Role = "candidate" | "employer" | "fsp_admin";

type AuthState =
  | { status: "loading"; me: null }
  | { status: "anonymous"; me: null }
  | { status: "authenticated"; me: MeOut };

interface AuthApi {
  status: AuthState["status"];
  me: MeOut | null;
  role: Role | null;
  login(email: string, password: string): Promise<void>;
  register(email: string, password: string, role: "candidate" | "employer"): Promise<void>;
  /** Вход по одноразовому токену из ссылки бота. */
  loginWithMagic(token: string): Promise<void>;
  /** Перечитать `/me` (например, после выдачи согласий). */
  reloadMe(): Promise<void>;
  logout(): Promise<void>;
}

const Ctx = createContext<AuthApi | null>(null);

/** Куда вести пользователя после входа и на что у него есть права. */
export const HOME_BY_ROLE: Record<Role, string> = {
  candidate: "/me",
  employer: "/employer",
  fsp_admin: "/federation",
};

/** Нужно ли сначала выдать обязательное согласие (`pd_processing`); админа ФСП это не касается. */
export function needsConsent(me: MeOut): boolean {
  return me.role !== "fsp_admin" && !me.consents.includes("pd_processing");
}

/** Куда вести вошедшего: на согласия, если их нет, иначе туда, откуда пришёл, или домой. */
export function postAuthPath(me: MeOut, from?: string): string {
  if (needsConsent(me)) return "/consents";
  return from ?? HOME_BY_ROLE[me.role as Role] ?? "/";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", me: null });

  // Тихий refresh при старте: access в памяти, refresh-cookie даёт новый.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (await refreshAccess()) {
          const res = await meMeGet();
          if (alive) return setState({ status: "authenticated", me: res.data as MeOut });
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

  const reloadMe = useCallback(async () => {
    const me = await meMeGet();
    setState({ status: "authenticated", me: me.data as MeOut });
  }, []);

  // Не-2xx мутатор бросает как ApiError, поэтому в `data` всегда успешный ответ.
  const signIn = useCallback(async (auth: unknown) => {
    setAccessToken((auth as AuthOut).access_token);
    // Кеш прежнего пользователя не должен попадать в кабинет нового (счётчики, списки).
    qc.clear();
    await reloadMe();
  }, [reloadMe, qc]);

  const login = useCallback(
    async (email: string, password: string) => signIn((await loginAuthLoginPost({ email, password })).data),
    [signIn],
  );

  const register = useCallback(
    async (email: string, password: string, role: "candidate" | "employer") =>
      signIn((await registerAuthRegisterPost({ email, password, role })).data),
    [signIn],
  );

  const loginWithMagic = useCallback(
    async (token: string) => signIn((await authMagicAuthMagicPost({ token })).data),
    [signIn],
  );

  const logout = useCallback(async () => {
    try {
      await logoutAuthLogoutPost();
    } finally {
      setAccessToken(null);
      qc.clear();
      setState({ status: "anonymous", me: null });
    }
  }, [qc]);

  const value = useMemo<AuthApi>(
    () => ({
      status: state.status,
      me: state.me,
      role: (state.me?.role as Role | undefined) ?? null,
      login,
      register,
      loginWithMagic,
      reloadMe,
      logout,
    }),
    [state, login, register, loginWithMagic, reloadMe, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth вне AuthProvider");
  return v;
}
