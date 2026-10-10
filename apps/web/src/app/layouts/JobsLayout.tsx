import CandidateLayout from "./CandidateLayout";
import PublicLayout from "./PublicLayout";
import { useAuth } from "@/shared/lib/auth";

/**
 * Каркас `/jobs` (E41-10): вошедшему кандидату вакансии открываются внутри кабинета (то же меню и шапка),
 * остальным — публичная раскладка. Адрес один и тот же, в том числе на корневом домене лендинга.
 */
export default function JobsLayout() {
  const { status, role } = useAuth();
  if (status === "loading") return <p role="status" className="p-6 text-muted">Загрузка…</p>;
  return status === "authenticated" && role === "candidate" ? <CandidateLayout /> : <PublicLayout />;
}
