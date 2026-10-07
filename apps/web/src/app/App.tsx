import { lazy, Suspense, type ComponentType } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { RequireRole } from "@/app/RequireRole";
import { ROUTES, SECTION_ROLE } from "@/app/routes";
import Consents from "@/pages/Consents";
import Login from "@/pages/Login";
import MagicLogin from "@/pages/MagicLogin";
import Onboarding from "@/pages/Onboarding";
import Profile from "@/features/profile/Profile";
import Home from "@/features/profile/Home";
import SkillEvidence from "@/features/profile/SkillEvidence";
import CandidateView from "@/features/employer/CandidateView";
import EmployerSearch from "@/features/employer/Search";
import Shortlist from "@/features/employer/Shortlist";
import ShortlistPage from "@/features/employer/ShortlistPage";
import Company from "@/features/employer/Company";
import Vacancies from "@/features/employer/Vacancies";
import VacancyEditor from "@/features/employer/VacancyEditor";
import OfferComposer from "@/features/offers/OfferComposer";
import { EmployerOfferDetail, EmployerOffers } from "@/features/offers/EmployerOffers";
import { CandidateOfferDetail, CandidateOffers } from "@/features/offers/CandidateOffers";
import NotFound from "@/pages/NotFound";
import Register from "@/pages/Register";
// >>> block1 imports
import Survey from "@/features/assessment/Survey";
import Attempt from "@/features/assessment/Attempt";
import Result from "@/features/assessment/Result";
import History from "@/features/assessment/History";
import VerifyEmail from "@/features/auth/VerifyEmail";
import ProfileEdit from "@/features/profile/ProfileEdit";
import Stats from "@/features/profile/Stats";
import Graph from "@/features/graph/Graph";
import CandidateTasks from "@/features/tasks/CandidateTasks";
import EmployerTasks from "@/features/tasks/EmployerTasks";
import Constructor from "@/features/constructor/Constructor";
import AdmissionQueue from "@/features/constructor/AdmissionQueue";
import AdminSkills from "@/features/admin-taxonomy/AdminSkills";
import AdminTaxonomy from "@/features/admin-taxonomy/AdminTaxonomy";
import DemoLlmExam from "@/features/demo/LlmExam";
import DemoNewProfession from "@/features/demo/NewProfession";
import DemoTwoWorlds from "@/features/demo/TwoWorlds";
// <<< block1 imports
// >>> block2 imports
import Landing from "@/features/landing/Landing";
import Legal from "@/features/landing/Legal";
import FederationDashboard from "@/features/admin/Dashboard";
import FederationModeration from "@/features/admin/Moderation";
import Quality from "@/features/quality/Quality";
import Fairness from "@/features/quality/Fairness";
import Runs from "@/features/quality/Runs";
import Navigator from "@/features/navigator/Navigator";
import Jobs from "@/features/jobs/Jobs";
import JobDetail from "@/features/jobs/JobDetail";
import CandidateResponses from "@/features/responses/CandidateResponses";
import EmployerResponses from "@/features/responses/EmployerResponses";
import NeedNew from "@/features/needs/NeedNew";
import NeedCategories from "@/features/needs/NeedCategories";
import CategoryCandidates from "@/features/needs/CategoryCandidates";
import Subscriptions from "@/features/needs/Subscriptions";
import { CandidateInterests } from "@/features/offers/CandidateInterests";
import EmployerMatch from "@/features/employer/Match";
// <<< block2 imports

// Разделы по ролям грузятся лениво (frontend.md: «ленивые разделы»).
const PublicLayout = lazy(() => import("@/app/layouts/PublicLayout"));
const CandidateLayout = lazy(() => import("@/app/layouts/CandidateLayout"));
const EmployerLayout = lazy(() => import("@/app/layouts/EmployerLayout"));
const AdminLayout = lazy(() => import("@/app/layouts/AdminLayout"));
const RunPage = lazy(() => import("@/features/runs/RunPage"));

// Старые адреса без своего экрана ведут на рабочий экран (E35-1: заглушек нет).
const redirects = (section: string) =>
  ROUTES.filter((r) => r.section === section && r.redirect).map((r) => (
    <Route key={r.path} path={r.path} element={<Navigate to={r.redirect!} replace />} />
  ));

function guarded(section: "candidate" | "employer" | "admin", Layout: ComponentType) {
  return (
    <Route element={<RequireRole role={SECTION_ROLE[section]!} />}>
      <Route element={<Layout />}>
        {redirects(section)}
        {section === "candidate" && (
          <>
            <Route path="/onboarding" element={<Onboarding />} />
            <Route path="/me" element={<Home />} />
            <Route path="/me/skills/:slug" element={<SkillEvidence />} />
            <Route path="/me/offers" element={<CandidateOffers />} />
            <Route path="/me/offers/:id" element={<CandidateOfferDetail />} />
            {/* >>> block1 (candidate) */}
            <Route path="/me/assessment" element={<Survey />} />
            <Route path="/me/assessment/history" element={<History />} />
            <Route path="/me/assessment/attempts/:id" element={<Attempt />} />
            <Route path="/me/assessment/attempts/:id/result" element={<Result />} />
            <Route path="/me/profile" element={<Profile />} />
            <Route path="/me/profile/edit" element={<ProfileEdit />} />
            <Route path="/me/stats" element={<Stats />} />
            <Route path="/me/tasks" element={<CandidateTasks />} />
            <Route path="/me/graph" element={<Graph />} />
            {/* <<< block1 (candidate) */}
            {/* >>> block2 (candidate) */}
            <Route path="/me/navigator" element={<Navigator />} />
            <Route path="/me/responses" element={<CandidateResponses />} />
            <Route path="/me/interests" element={<CandidateInterests />} />
            {/* <<< block2 (candidate) */}
          </>
        )}
        {section === "employer" && (
          <>
            <Route path="/employer/search" element={<EmployerSearch />} />
            <Route path="/employer/candidates/:id" element={<CandidateView />} />
            <Route path="/employer/vacancies" element={<Vacancies />} />
            <Route path="/employer/vacancies/new" element={<VacancyEditor />} />
            <Route path="/employer/vacancies/:id" element={<VacancyEditor />} />
            <Route path="/employer/company" element={<Company />} />
            <Route path="/employer/offers/new" element={<OfferComposer />} />
            <Route path="/employer/offers" element={<EmployerOffers />} />
            <Route path="/employer/offers/:id" element={<EmployerOfferDetail />} />
            <Route path="/employer/vacancies/:id/shortlist" element={<Shortlist />} />
            <Route path="/employer/shortlist" element={<ShortlistPage />} />
            {/* >>> block1 (employer) */}
            <Route path="/employer/tasks" element={<EmployerTasks />} />
            <Route path="/employer/families/new" element={<Constructor />} />
            {/* <<< block1 (employer) */}
            {/* >>> block2 (employer) */}
            <Route path="/employer" element={<EmployerMatch />} />
            <Route path="/employer/responses" element={<EmployerResponses />} />
            <Route path="/employer/needs/new" element={<NeedNew />} />
            <Route path="/employer/needs/:id" element={<NeedCategories />} />
            <Route path="/employer/categories/:profession/:grade" element={<CategoryCandidates />} />
            <Route path="/employer/subscriptions" element={<Subscriptions />} />
            {/* <<< block2 (employer) */}
          </>
        )}
        {section === "admin" && (
          <>
            {/* >>> block1 (admin) */}
            <Route path="/admin/families" element={<AdmissionQueue />} />
            <Route path="/admin/professions" element={<AdminTaxonomy />} />
            <Route path="/admin/skills" element={<AdminSkills />} />
            <Route path="/admin/demo/two-worlds" element={<DemoTwoWorlds />} />
            <Route path="/admin/demo/llm-exam" element={<DemoLlmExam />} />
            <Route path="/admin/demo/new-profession" element={<DemoNewProfession />} />
            {/* <<< block1 (admin) */}
            {/* >>> block2 (admin) */}
            <Route path="/federation" element={<FederationDashboard />} />
            <Route path="/federation/moderation" element={<FederationModeration />} />
            <Route path="/admin/quality" element={<Quality />} />
            <Route path="/admin/quality/fairness" element={<Fairness />} />
            <Route path="/admin/quality/runs" element={<Runs />} />
            {/* <<< block2 (admin) */}
          </>
        )}
      </Route>
    </Route>
  );
}

export function App() {
  return (
    <Suspense fallback={<p role="status" className="p-6 text-muted">Загрузка…</p>}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/auth/magic" element={<MagicLogin />} />
          <Route path="/consents" element={<Consents />} />
          {/* >>> block1 (auth) */}
          <Route path="/verify-email" element={<VerifyEmail />} />
          {/* <<< block1 (auth) */}
          {/* >>> block2 (auth) */}
          {/* <<< block2 (auth) */}
          {/* >>> block1 (public) */}
          {/* <<< block1 (public) */}
          {/* >>> block2 (public) */}
          <Route path="/" element={<Landing />} />
          <Route path="/run/:token" element={<RunPage />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/terms" element={<Legal />} />
          <Route path="/privacy" element={<Legal />} />
          {/* <<< block2 (public) */}
        </Route>
        {guarded("candidate", CandidateLayout)}
        {guarded("employer", EmployerLayout)}
        {guarded("admin", AdminLayout)}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
