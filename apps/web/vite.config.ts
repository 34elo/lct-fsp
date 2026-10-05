import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { loadEnv, type ProxyOptions } from "vite";
import { defineConfig } from "vitest/config";

const LOCAL = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(\/|$)/;

/** Прокси /api на VITE_API_TARGET. Удалённой цели подставляем её Origin: core проверяет Origin на cookie-эндпоинтах. */
export function apiProxy(target: string): string | ProxyOptions {
  if (LOCAL.test(target)) return target;
  return { target, changeOrigin: true, headers: { Origin: new URL(target).origin } };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const target = env.VITE_API_TARGET || "http://localhost:28080";
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
      dedupe: ["react", "react-dom"],
    },
    server: { port: 28173, proxy: { "/api": apiProxy(target) } },
    test: { environment: "jsdom", globals: true, setupFiles: ["./src/test-setup.ts"], css: false },
  };
});
