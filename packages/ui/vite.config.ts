import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

// Vite обслуживает playground (порт 28174); vitest гоняет тесты src/.
export default defineConfig({
  root: here("./playground"),
  publicDir: here("../../apps/web/public"),
  plugins: [react(), tailwindcss()],
  server: { port: 28174, strictPort: true },
  build: { outDir: here("./dist"), emptyOutDir: true },
  test: {
    root: here("."),
    include: ["src/**/*.test.{ts,tsx}", "scripts/**/*.test.mjs"],
    environment: "jsdom",
    globals: true,
    setupFiles: [here("./src/test-setup.ts")],
    css: false,
  },
});
