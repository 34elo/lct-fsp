import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { Providers, makeQueryClient } from "@/app/Providers";
import { setAccessToken } from "@/shared/lib/token";

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const problem = (status: number, code: string) => res(status, { code, status, title: "x", type: "x" });
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const calls: { url: string; method: string; body: any }[] = [];
let queue: unknown[];
let merges: unknown[];
let distinct: unknown[];
let blocklist: unknown[];
let provisional: unknown[];
let hints: unknown;
let revertReply: () => Response;
let mergeReply: () => Response;

const brief = (slug: string, name: string, status: string) => ({ slug, name, status, support_candidates: 2, support_vacancies: 1 });

beforeEach(() => {
  calls.length = 0;
  queue = [
    {
      skill: "postgres-sql", skill_name: "Postgres SQL", into: "postgresql", into_name: "PostgreSQL", confidence: 0.8, norm: "postgres sql",
      from: brief("postgres-sql", "Postgres SQL", "provisional"), target: brief("postgresql", "PostgreSQL", "active"),
      preview: { aliases: ["postgres sql", "postgres-sql"], relations: 3, support_candidates: 2, support_vacancies: 1 },
    },
  ];
  merges = [{ id: "m1", from_skill: "k8s", from_name: "K8s", into_skill: "kubernetes", into_name: "Kubernetes", actor: "pipeline", created_at: "2026-10-01T10:00:00Z", reverted_at: null, aliases_added: 2, rows_moved: 5 }];
  distinct = [{ a: "java", b: "javascript", a_name: "Java", b_name: "JavaScript" }];
  blocklist = [{ norm: "мусор", reason: "шум", created_at: "2026-10-01T10:00:00Z" }];
  provisional = [{ ...brief("helmfile", "Helmfile", "provisional"), type: "hard", created_at: "2026-10-02T10:00:00Z", draft: { summary: "Описание helmfile" } }];
  hints = {
    updated_at: "2026-10-03T00:00:00+00:00",
    discipline_rules: [{ discipline: "algo", discipline_name: "Алгоритмы", skill: "graphs", lift: 2.5, support: 12 }],
    profession_candidates: [{ skills: ["unity", "csharp"], support: 7, covered_by_professions: 0.1 }],
  };
  revertReply = () => res(200, { taxonomy_version: 7 });
  mergeReply = () => res(200, { id: "m2", from_skill: "postgres-sql", into_skill: "postgresql", taxonomy_version: 8 });
  setAccessToken(null);
  vi.stubGlobal("EventSource", class { addEventListener() {} close() {} });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined });
      if (url.endsWith("/auth/refresh")) return res(200, { access_token: "t" });
      if (url.endsWith("/auth/me") || url.endsWith("/me")) return res(200, { id: "u1", email: "a@b.ru", role: "fsp_admin", consents: ["pd_processing"] });
      if (url.endsWith("/admin/skills/queue")) return res(200, queue);
      if (url.endsWith("/admin/skills/queue/postgres-sql/approve")) return mergeReply();
      if (url.endsWith("/admin/skills/queue/postgres-sql/reject")) return res(200, { taxonomy_version: 8 });
      if (url.endsWith("/admin/skills/merges")) return res(200, merges);
      if (url.endsWith("/admin/skills/merges/m1/revert")) return revertReply();
      if (url.includes("/admin/skills/distinct") && method === "POST") return res(200, { changed: true, taxonomy_version: 9 });
      if (url.includes("/admin/skills/distinct") && method === "DELETE") return res(200, { changed: true, taxonomy_version: 9 });
      if (url.endsWith("/admin/skills/distinct")) return res(200, distinct);
      if (url.includes("/admin/skills/blocklist") && method === "POST") return res(200, { norm: "ёлки", reason: null, created_at: "2026-10-01T10:00:00Z" });
      if (url.includes("/admin/skills/blocklist") && method === "DELETE") return res(204);
      if (url.endsWith("/admin/skills/blocklist")) return res(200, blocklist);
      if (url.endsWith("/admin/skills/provisional")) return res(200, provisional);
      if (url.endsWith("/admin/skills/helmfile/approve")) return res(200, brief("helmfile", "Helmfile", "active"));
      if (url.endsWith("/admin/skills/hints")) return res(200, hints);
      return problem(404, "not_found");
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount() {
  render(
    <MemoryRouter initialEntries={["/admin/skills"]}>
      <Providers client={makeQueryClient()}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
}
const tab = async (t: string) => fireEvent.click(await screen.findByTestId(`admin-sk-tab-${t}`));
const last = (m: string, part: string) => calls.filter((c) => c.method === m && c.url.includes(part)).at(-1);

describe("/admin/skills", () => {
  it("очередь: превью и слияние", async () => {
    mount();
    expect(await screen.findByTestId("admin-sk-preview-postgres-sql")).toHaveTextContent("postgres sql");
    expect(screen.getByTestId("admin-sk-preview-postgres-sql")).toHaveTextContent("связей перейдёт: 3");
    expect(screen.getByTestId("admin-sk-confidence-postgres-sql")).toHaveTextContent("80%");
    fireEvent.click(screen.getByTestId("admin-sk-merge-postgres-sql"));
    expect(await screen.findByTestId("admin-sk-notice")).toHaveTextContent("влит в «PostgreSQL»");
    expect(last("POST", "/queue/postgres-sql/approve")).toBeTruthy();
  });

  it("очередь: отклонение с пометкой «точно разные»", async () => {
    mount();
    fireEvent.click(await screen.findByTestId("admin-sk-distinct-check-postgres-sql"));
    fireEvent.click(screen.getByTestId("admin-sk-reject-postgres-sql"));
    await screen.findByTestId("admin-sk-notice");
    expect(last("POST", "/queue/postgres-sql/reject")?.body).toEqual({ mark_distinct: true });
  });

  it("слияние запрещено парой «точно разные»: понятная ошибка", async () => {
    mergeReply = () => problem(409, "merge_forbidden_distinct");
    mount();
    fireEvent.click(await screen.findByTestId("admin-sk-merge-postgres-sql"));
    expect(await screen.findByTestId("admin-sk-error")).toHaveTextContent("«точно разные»");
  });

  it("журнал: откат слияния с подтверждением", async () => {
    mount();
    await tab("merges");
    fireEvent.click(await screen.findByTestId("admin-sk-revert-k8s"));
    expect(last("POST", "/revert")).toBeUndefined();
    fireEvent.click(await screen.findByTestId("admin-sk-revert-yes-k8s"));
    expect(await screen.findByTestId("admin-sk-notice")).toHaveTextContent("откатано");
    expect(last("POST", "/merges/m1/revert")).toBeTruthy();
  });

  it("журнал: ошибка отката", async () => {
    revertReply = () => problem(409, "merge_not_revertible");
    mount();
    await tab("merges");
    fireEvent.click(await screen.findByTestId("admin-sk-revert-k8s"));
    fireEvent.click(await screen.findByTestId("admin-sk-revert-yes-k8s"));
    expect(await screen.findByTestId("admin-sk-error")).toHaveTextContent("более позднее слияние");
  });

  it("«точно разные»: добавление и удаление", async () => {
    mount();
    await tab("distinct");
    expect(await screen.findByTestId("admin-sk-distinct-row-java-javascript")).toHaveTextContent("Java ≠ JavaScript");
    fireEvent.click(screen.getByTestId("admin-sk-distinct-add"));
    expect(await screen.findByTestId("admin-sk-error")).toHaveTextContent("оба идентификатора");
    fireEvent.change(screen.getByTestId("admin-sk-distinct-a"), { target: { value: "c" } });
    fireEvent.change(screen.getByTestId("admin-sk-distinct-b"), { target: { value: "csharp" } });
    fireEvent.click(screen.getByTestId("admin-sk-distinct-add"));
    await waitFor(() => expect(last("POST", "/distinct")?.body).toEqual({ a: "c", b: "csharp" }));
    fireEvent.click(screen.getByTestId("admin-sk-distinct-remove-java-javascript"));
    await waitFor(() => expect(last("DELETE", "/distinct")?.url).toContain("a=java&b=javascript"));
  });

  it("стоп-лист: добавление и удаление", async () => {
    mount();
    await tab("blocklist");
    expect(await screen.findByTestId("admin-sk-blocklist-row-мусор")).toHaveTextContent("шум");
    fireEvent.change(screen.getByTestId("admin-sk-blocklist-norm"), { target: { value: "Ёлки" } });
    fireEvent.click(screen.getByTestId("admin-sk-blocklist-add"));
    await waitFor(() => expect(last("POST", "/blocklist")?.body).toEqual({ norm: "Ёлки", reason: null }));
    fireEvent.click(screen.getByTestId("admin-sk-blocklist-remove-мусор"));
    await waitFor(() => expect(last("DELETE", "/blocklist")?.url).toContain("norm="));
  });

  it("новые навыки: черновик карточки и подтверждение", async () => {
    mount();
    await tab("provisional");
    expect(await screen.findByTestId("admin-sk-prov-draft-helmfile")).toHaveTextContent("Описание helmfile");
    fireEvent.click(screen.getByTestId("admin-sk-prov-approve-helmfile"));
    expect(await screen.findByTestId("admin-sk-notice")).toHaveTextContent("«Helmfile» подтверждён");
  });

  it("подсказки роста", async () => {
    mount();
    await tab("hints");
    expect(await screen.findByTestId("admin-sk-hints-disciplines")).toHaveTextContent("Алгоритмы");
    expect(screen.getByTestId("admin-sk-hints-professions")).toHaveTextContent("unity");
    expect(screen.getByTestId("admin-sk-hints-professions")).toHaveTextContent("покрыто профессиями: 10%");
  });

  it("пустая очередь", async () => {
    queue = [];
    mount();
    expect(await screen.findByText("Очередь пуста")).toBeInTheDocument();
  });
});
