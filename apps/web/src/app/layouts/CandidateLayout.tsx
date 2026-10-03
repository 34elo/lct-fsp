import { NAV } from "@/app/routes";
import { Shell } from "./Shell";

export default function CandidateLayout() {
  return <Shell nav={NAV.candidate} variant="top" />;
}
