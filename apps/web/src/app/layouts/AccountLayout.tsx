import { useAuth } from "@/shared/lib/auth";
import AdminLayout from "./AdminLayout";
import CandidateLayout from "./CandidateLayout";
import EmployerLayout from "./EmployerLayout";

/** Каркас общих экранов (`/settings`): тот же, что у кабинета роли, чтобы шапка и меню не менялись. */
export default function AccountLayout() {
  const { role } = useAuth();
  if (role === "employer") return <EmployerLayout />;
  if (role === "fsp_admin") return <AdminLayout />;
  return <CandidateLayout />;
}
