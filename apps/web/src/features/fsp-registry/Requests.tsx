import { AdminPageHeader } from "@/features/admin/PageHeader";
import { PAGE } from "@/shared/lib/page";

import { Requests } from "./FspRegistry";
import { R } from "./text";

/** `/federation/requests` — очередь заявок на привязку ФСП (E39-29, группа «Очереди»). */
export default function FspRequests() {
  return (
    <div className={PAGE.wide}>
      <AdminPageHeader title={R.requests.title} tip={R.requests.lead} />
      <Requests />
    </div>
  );
}
