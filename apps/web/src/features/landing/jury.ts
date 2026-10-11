/** Вход жюри: включается `VITE_JURY_MODE=true` при сборке стенда. Пароль не нужен:
 * `POST /auth/jury` выдаёт свою песочницу (кандидат + работодатель), см. `useAuth().loginAsJury`. */
export const JURY = {
  candidate: { to: "/me/assessment?mode=express" },
  employer: { to: "/employer/search" },
} as const;

export const juryEnabled = (): boolean => import.meta.env.VITE_JURY_MODE === "true";
