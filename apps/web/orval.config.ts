import { defineConfig } from "orval";

// `pnpm api:gen` берёт живую схему core; без неё — снимок схемы core (apps/web/openapi.json, без /internal).
const input = process.env.OPENAPI_URL ?? "./openapi.json";

export default defineConfig({
  fsp: {
    input,
    output: {
      mode: "tags-split",
      target: "src/api/endpoints",
      schemas: "src/api/model",
      client: "react-query",
      clean: true,
      override: { mutator: { path: "src/api/mutator.ts", name: "apiFetch" } },
    },
  },
});
