import { Outlet } from "react-router-dom";

import { cn } from "@fsp/ui";

import { useListOffersOffersGet, useMyInterestsCandidatesMeInterestsGet, useMyOffersCandidatesMeOffersGet } from "@/api/endpoints/offers/offers";
import { type NavItem } from "@/app/routes";
import { useAuth } from "@/shared/lib/auth";
import { AdminSidebar } from "./AdminSidebar";
import { AppHeader } from "./AppHeader";
import { BottomNav } from "./BottomNav";
import { PageContainer } from "./PageContainer";
import { CANDIDATE_BOTTOM } from "./shell-meta";

export { ThemeToggle } from "./AppHeader";

/** Счётчик «Офферы» в шапке (если API ответил). Запрос только для своей роли. */
function useOfferCounts(variant: "top" | "side"): Record<string, number | undefined> {
  const { role } = useAuth();
  const employer = useListOffersOffersGet(undefined, { query: { enabled: variant === "top" && role === "employer", retry: false } });
  const candidate = useMyOffersCandidatesMeOffersGet(undefined, { query: { enabled: variant === "top" && role === "candidate", retry: false } });
  const interests = useMyInterestsCandidatesMeInterestsGet({ query: { enabled: variant === "top" && role === "candidate", retry: false } });
  const n = (q: { data?: { status: number; data: unknown } }) =>
    q.data?.status === 200 && Array.isArray(q.data.data) ? q.data.data.length : undefined;
  return { "/employer/offers": n(employer), "/me/offers": n(candidate), "/me/interests": interests.data?.status === 200 ? interests.data.data.companies : undefined };
}

/**
 * Каркас по ролям (E19-5). Кабинеты кандидата и работодателя: шапка с вкладками на десктопе,
 * у кандидата на ≤768 px ещё и нижняя панель; админка — боковая панель.
 */
export function Shell({ nav, variant }: { nav: NavItem[]; variant: "top" | "side" }) {
  const { role } = useAuth();
  const counts = useOfferCounts(variant);
  const bottom = variant === "top" && role === "candidate";
  return (
    <div className={cn("min-h-dvh bg-page text-ink", variant === "side" && "md:grid md:grid-cols-[220px_1fr]")}>
      {variant === "side" && <AdminSidebar nav={nav} />}
      <div className="flex min-h-dvh min-w-0 flex-col">
        <AppHeader nav={nav} counts={counts} withTabs={variant === "top"} />
        {/* Поля задают сами страницы (p-4 md:p-6), поэтому контейнер без своих полей. */}
        <PageContainer className={cn("flex-1 px-0 md:px-0 lg:px-0", bottom && "pb-20 md:pb-0")} as="main">
          <Outlet />
        </PageContainer>
        {bottom && <BottomNav items={CANDIDATE_BOTTOM} all={nav} />}
      </div>
    </div>
  );
}
