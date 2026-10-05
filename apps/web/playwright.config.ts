import { defineConfig, devices } from "@playwright/test";

/**
 * e2e на стенде с сидом (`make up && make seed`): E2E_BASE_URL — gateway (по умолчанию 28080).
 * Запуск: `make e2e` (всё) или `pnpm e2e e2e/b1-*` (файлы блока). Файлы: b1-* (кандидат и тест),
 * b2-* (работодатель и подбор), joint-* (сквозные, пишет стыковка).
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: /(b1|b2|joint)-.*\.spec\.ts$/,
  timeout: 30_000,
  retries: 0,
  workers: 1, // демо-данные общие: тесты не должны мешать друг другу
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:28080",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-375", use: { ...devices["Desktop Chrome"], viewport: { width: 375, height: 812 } } },
  ],
});
