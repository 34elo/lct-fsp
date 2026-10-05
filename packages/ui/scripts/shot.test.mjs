import { demoAccount, normalizeRoute, shotName } from "./shot.mjs";

const YAML = `demo:
  password: "demo-pass-1234"
  candidate_email: "cand{n:04d}@demo.fsp.test"
  employer_email: "hr{n:02d}@demo.fsp.test"
  admin_email: "admin@demo.fsp.test"
`;

test("демо-аккаунт берётся из seed-конфига", () => {
  expect(demoAccount("employer", YAML)).toEqual({ email: "hr01@demo.fsp.test", password: "demo-pass-1234" });
  expect(demoAccount("candidate", YAML).email).toBe("cand0001@demo.fsp.test");
  expect(demoAccount("admin", YAML).email).toBe("admin@demo.fsp.test");
});

test("маршрут нормализуется, в том числе после Git Bash", () => {
  expect(normalizeRoute("/employer/search")).toBe("/employer/search");
  expect(normalizeRoute("#brand")).toBe("/#brand");
  expect(normalizeRoute("C:/Program Files/Git/employer/search")).toBe("/employer/search");
});

test("имя файла из маршрута", () => {
  expect(shotName("/employer/search", false)).toBe("employer-search");
  expect(shotName("/", false)).toBe("root");
  expect(shotName("/#brand", true)).toBe("playground-brand");
});
