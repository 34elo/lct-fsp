import { lazy, Suspense, type ComponentType } from "react";
import { Route, Routes } from "react-router-dom";

import { RequireRole } from "@/app/RequireRole";
import { ROUTES, SECTION_ROLE } from "@/app/routes";
import Login from "@/pages/Login";
import NotFound from "@/pages/NotFound";
import { Stub } from "@/pages/Stub";

// Разделы по ролям грузятся лениво (frontend.md: «ленивые разделы»).
const PublicLayout = lazy(() => import("@/app/layouts/PublicLayout"));
const CandidateLayout = lazy(() => import("@/app/layouts/CandidateLayout"));
const EmployerLayout = lazy(() => import("@/app/layouts/EmployerLayout"));
const AdminLayout = lazy(() => import("@/app/layouts/AdminLayout"));

const stubs = (section: string) =>
  ROUTES.filter((r) => r.section === section && r.path !== "/login").map((r) => (
    <Route key={r.path} path={r.path} element={<Stub routePath={r.path} />} />
  ));

function guarded(section: "candidate" | "employer" | "admin", Layout: ComponentType) {
  return (
    <Route element={<RequireRole role={SECTION_ROLE[section]!} />}>
      <Route element={<Layout />}>{stubs(section)}</Route>
    </Route>
  );
}

export function App() {
  return (
    <Suspense fallback={<p role="status" className="p-6 text-muted">Загрузка…</p>}>
      <Routes>
        <Route element={<PublicLayout />}>
          {stubs("public")}
          <Route path="/login" element={<Login />} />
          {stubs("auth")}
        </Route>
        {guarded("candidate", CandidateLayout)}
        {guarded("employer", EmployerLayout)}
        {guarded("admin", AdminLayout)}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
