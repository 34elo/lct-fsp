import { expect, test } from "@playwright/test";
import { apiLogin, bearer } from "./fixtures";

test("Аня входит и получает профиль и грейды", async ({ request }) => {
  const h = bearer(await apiLogin(request, "anya"));
  expect((await request.get("/api/v1/candidates/me/profile", { headers: h })).status()).toBe(200);
});
