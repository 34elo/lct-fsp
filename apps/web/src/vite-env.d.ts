/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Адрес кабинета (dashboard.), на который ведут кнопки лендинга на корневом домене; пусто — тот же origin. */
  readonly VITE_APP_URL?: string;
}
