import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { validateContacts } from "@/features/profile/ProfileEdit";
import { downloadProfilePdf } from "@/features/profile/pdf";
import { setAccessToken } from "@/shared/lib/token";

const json = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });

const profile = {
  pseudonym: "Backend #4821",
  profile_version: 3,
  search_status: "active",
  active_until: "2026-10-20T00:00:00Z",
  preferences: { work_format: [], relocation: false },
  visibility: { public_profile: false, teams: true },
  claimed_soft: ["Коммуникация"],
  experience: [],
  contacts: { email: "me@x.ru", phone: null, telegram: null },
  experience_months: 24,
  desired_roles: ["backend"],
  grade: { breakdown: [] },
  skills: [{ skill: { slug: "python", name: "Python", group: "language" }, confidence: 0.2, level: 1, sources: ["self"], claimed_only: true, status: "active", derived_from: null, top_evidence: [] }],
  team_signals: [],
};
const taxonomy = {
  version: "1",
  skills: [
    { slug: "python", name: "Python", kind: "hard" },
    { slug: "redis", name: "Redis", kind: "hard" },
    { slug: "communication", name: "Коммуникация", kind: "soft" },
    { slug: "teamwork", name: "Работа в команде", kind: "soft" },
  ],
};

class FakeES {
  addEventListener() {}
  close() {}
}

function install(patch: () => Response = () => json(200, profile)) {
  const bodies: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "t" });
      if (url.endsWith("/me")) return json(200, { id: "u1", email: "a@b.ru", role: "candidate", email_verified: true, consents: ["pd_processing"] });
      if (url.endsWith("/taxonomy")) return json(200, taxonomy);
      if (url.endsWith("/candidates/me/profile") && init?.method === "PATCH") {
        bodies.push(JSON.parse(String(init.body)));
        return patch();
      }
      if (url.endsWith("/candidates/me/profile")) return json(200, profile);
      return json(404);
    }),
  );
  return bodies;
}

function mount(path = "/me/profile/edit") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setAccessToken(null);
  vi.stubGlobal("EventSource", FakeES);
});
afterEach(() => vi.unstubAllGlobals());

test("форма подставляет данные профиля и отправляет PATCH без нетронутых стека и софта", async () => {
  const bodies = install();
  mount();
  expect(await screen.findByTestId("profile-edit-email")).toHaveValue("me@x.ru");
  expect(screen.getByTestId("profile-edit-months")).toHaveValue("24");
  expect(screen.getByTestId("profile-edit-role-backend")).toHaveAttribute("aria-pressed", "true");
  fireEvent.change(screen.getByTestId("profile-edit-phone"), { target: { value: "+7 900 123-45-67" } });
  fireEvent.click(screen.getByTestId("profile-edit-save"));
  expect(await screen.findByTestId("profile-edit-saved")).toBeInTheDocument();
  expect(bodies[0]).toEqual({
    contacts: { email: "me@x.ru", phone: "+7 900 123-45-67", telegram: null },
    experience_months: 24,
    desired_roles: ["backend"],
  });
});

test("добавление навыка в стек и софт-качества уходит в PATCH полным списком", async () => {
  const bodies = install();
  mount();
  fireEvent.change(await screen.findByTestId("profile-edit-stack-search"), { target: { value: "red" } });
  fireEvent.click(await screen.findByTestId("profile-edit-stack-add-redis"));
  fireEvent.click(screen.getByTestId("profile-edit-soft-teamwork"));
  fireEvent.click(screen.getByTestId("profile-edit-save"));
  await screen.findByTestId("profile-edit-saved");
  const b = bodies[0] as { stack: { slug: string }[]; soft_skills: string[] };
  expect(b.stack.map((s) => s.slug)).toEqual(["python", "redis"]);
  expect(b.soft_skills.sort()).toEqual(["communication", "teamwork"]);
});

test("15–17 лет: без согласия родителя предупреждение, с согласием — в PATCH", async () => {
  const bodies = install();
  mount();
  fireEvent.click(await screen.findByTestId("profile-edit-age-minor"));
  expect(screen.getByTestId("profile-edit-age-hidden")).toBeInTheDocument();
  fireEvent.click(screen.getByTestId("profile-edit-age-parent"));
  expect(screen.queryByTestId("profile-edit-age-hidden")).toBeNull();
  fireEvent.click(screen.getByTestId("profile-edit-save"));
  await screen.findByTestId("profile-edit-saved");
  expect(bodies[0]).toMatchObject({ age_group: "minor", parent_consent: true });
});

test("невалидная почта блокирует отправку", async () => {
  const bodies = install();
  mount();
  fireEvent.change(await screen.findByTestId("profile-edit-email"), { target: { value: "nope" } });
  fireEvent.click(screen.getByTestId("profile-edit-save"));
  expect(await screen.findByText("Проверьте адрес почты")).toBeInTheDocument();
  expect(bodies).toHaveLength(0);
});

test("422 unknown_skill показывается по-русски", async () => {
  install(() => json(422, { code: "unknown_skill" }));
  mount();
  fireEvent.click(await screen.findByTestId("profile-edit-save"));
  expect(await screen.findByTestId("profile-edit-error")).toHaveTextContent("нет в справочнике");
});

test("не более 5 желаемых ролей", async () => {
  install();
  mount();
  await screen.findByTestId("profile-edit-roles");
  for (const r of ["frontend", "fullstack", "ml", "qa", "devops"]) fireEvent.click(screen.getByTestId(`profile-edit-role-${r}`));
  expect(screen.getByTestId("profile-edit-role-devops")).toHaveAttribute("aria-pressed", "false");
});

test("validateContacts", () => {
  expect(validateContacts({ email: "", phone: "", telegram: "", months: "" })).toEqual({});
  expect(Object.keys(validateContacts({ email: "x", phone: "12", telegram: "ab", months: "700" })).sort()).toEqual(["email", "months", "phone", "telegram"]);
});

test("скачивание PDF: запрос с Bearer, при ошибке false", async () => {
  setAccessToken("tok");
  const created = vi.fn(() => "blob:x");
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const f = vi.fn(async () => new Response("%PDF", { status: 200 }));
  vi.stubGlobal("fetch", f);
  expect(await downloadProfilePdf("Backend")).toBe(true);
  const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe("/api/v1/candidates/me/profile.pdf");
  expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  expect(click).toHaveBeenCalled();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 403 })));
  expect(await downloadProfilePdf("Backend")).toBe(false);
  await waitFor(() => expect(created).toHaveBeenCalledTimes(1));
});
