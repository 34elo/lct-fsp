// @vitest-environment node
import { apiProxy } from "./vite.config";

test("локальная цель прокси — как есть", () => {
  expect(apiProxy("http://localhost:28080")).toBe("http://localhost:28080");
  expect(apiProxy("http://127.0.0.1:28080/")).toBe("http://127.0.0.1:28080/");
});

test("удалённой цели подставляется Origin", () => {
  expect(apiProxy("https://fsp.example.test/base")).toEqual({
    target: "https://fsp.example.test/base",
    changeOrigin: true,
    headers: { Origin: "https://fsp.example.test" },
  });
});
