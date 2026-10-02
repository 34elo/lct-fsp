import { NAV } from "@/app/routes";
import { Shell } from "./Shell";

export default function AdminLayout() {
  return <Shell nav={NAV.admin} variant="side" />;
}
