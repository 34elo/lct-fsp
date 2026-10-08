/** Вход жюри (E32-4b): включается `VITE_JURY_MODE=true` при сборке стенда. Аккаунты и тестовый пароль — tools/seed/config.yaml. */
export const JURY = {
  password: "demo-pass-1234",
  candidate: { email: "jury-candidate@demo.fsp.test", to: "/me/assessment?mode=express" },
  employer: { email: "jury-hr@demo.fsp.test", to: "/employer/search" },
} as const;

export const juryEnabled = (): boolean => import.meta.env.VITE_JURY_MODE === "true";
