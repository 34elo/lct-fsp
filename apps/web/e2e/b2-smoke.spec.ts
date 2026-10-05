import { expect, test } from "@playwright/test";
import { apiLogin, bearer } from "./fixtures";

test("b2: Ольга входит и видит свои офферы", async ({ request }) => {
  const h = bearer(await apiLogin(request, "olga"));
  expect((await request.get("/api/offers", { headers: h })).status()).toBe(200);
});

test("b2: чужой оффер → 404", async ({ request }) => {
  const h = bearer(await apiLogin(request, "anya"));
  const r = await request.get("/api/offers/00000000-0000-0000-0000-000000000001", { headers: h });
  expect(r.status()).toBe(404);
});
