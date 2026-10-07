import { NAV } from "@/app/routes";
import { PathBanner } from "@/features/assessment/PathBanner";
import { Shell } from "./Shell";

export default function CandidateLayout() {
  return <Shell nav={NAV.candidate} variant="top" banner={<PathBanner />} />;
}
