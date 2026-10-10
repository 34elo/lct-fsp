import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { refreshAccess } from "@/api/mutator";
import {
  authMagicAuthMagicPost,
  juryEnterAuthJuryPost,
  loginAuthLoginPost,
  logoutAuthLogoutPost,
  meMeGet,
  registerAuthRegisterPost,
} from "@/api/endpoints/auth/auth";
import { putConsentsMeConsentsPut } from "@/api/endpoints/consents/consents";
import type { AuthOut, ConsentType, JuryAuthOut, MeOut } from "@/api/model";
import { setAccessToken } from "@/shared/lib/token";

export type Role = "candidate" | "employer" | "fsp_admin";

/** Ключ песочницы жюри (E40-1): тот же браузер возвращается в свою пару «кандидат + работодатель». */
const JURY_PAIR_KEY = "fsp.jury.pair";

function readJuryPair(): string | null {
  try {
    return localStorage.getItem(JURY_PAIR_KEY);
  } catch {
    return null;
  }
}

function saveJuryPair(pair: string): void {
  try {
    localStorage.setItem(JURY_PAIR_KEY, pair);
  } catch {
    /* без хранилища — каждый вход в новую песочницу */
  }
}

type AuthState =
  | { status: "loading"; me: null }
  | { status: "anonymous"; me: null }
  | { status: "authenticated"; me: MeOut };

interface AuthApi {
  status: AuthState["status"];
  me: MeOut | null;
  role: Role | null;
  login(email: string, password: string): Promise<void>;
  /** `consents` — обязательные согласия, отмеченные в форме регистрации (E39-6): выдаются сразу. */
  register(email: string, password: string, role: "candidate" | "employer", consents?: ConsentType[]): Promise<void>;
  /** Вход по одноразовому токену из ссылки бота. */
  loginWithMagic(token: string): Promise<void>;
  /** Вход «Демо для жюри» в свою песочницу (E40-1): без пароля, только на демо-стенде. */
  loginAsJury(role: "candidate" | "employer"): Promise<void>;
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

/** Вход временным паролем HR (E41-16): до смены пароля другие экраны закрыты. */
export const PASSWORD_SETUP_PATH = "/password/new";

/** Куда вести вошедшего: сменить временный пароль, на согласия, туда, откуда пришёл, или домой. */
export function postAuthPath(me: MeOut, from?: string): string {
  if (me.must_change_password) return PASSWORD_SETUP_PATH;
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
    async (email: string, password: string, role: "candidate" | "employer", consents: ConsentType[] = []) => {
      const auth = (await registerAuthRegisterPost({ email, password, role })).data;
      if (consents.length) {
        setAccessToken((auth as AuthOut).access_token);
        try {
          await putConsentsMeConsentsPut({ consents: consents.map((type) => ({ type, granted: true })) });
        } catch {
          // Не выдали — после входа `postAuthPath` поведёт на экран согласий.
        }
      }
      try {
        await signIn(auth);
      } catch {
        // Аккаунт уже создан: одно повторное чтение профиля, а не ложная ошибка входа (E35-7a).
        await signIn(auth);
      }
    },
    [signIn],
  );

  const loginWithMagic = useCallback(
    async (token: string) => signIn((await authMagicAuthMagicPost({ token })).data),
    [signIn],
  );

  const loginAsJury = useCallback(
    async (role: "candidate" | "employer") => {
      const auth = (await juryEnterAuthJuryPost({ role, pair: readJuryPair() })).data as JuryAuthOut;
      saveJuryPair(auth.pair);
      await signIn(auth);
    },
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
      loginAsJury,
      reloadMe,
      logout,
    }),
    [state, login, register, loginWithMagic, loginAsJury, reloadMe, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Сессия и действия входа из `AuthProvider`: пользователь, login/register/magic, logout, перезагрузка `/me`. */
export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth вне AuthProvider");
  return v;
}
