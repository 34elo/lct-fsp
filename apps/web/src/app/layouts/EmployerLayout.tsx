import { NAV } from "@/app/routes";
import { Shell } from "./Shell";

export default function EmployerLayout() {
  return <Shell nav={NAV.employer} variant="top" />;
}
