import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";

import { cn } from "@fsp/ui";

import { useListOffersOffersGet, useMyInterestsCandidatesMeInterestsGet, useMyOffersCandidatesMeOffersGet } from "@/api/endpoints/offers/offers";
import { type NavItem } from "@/app/routes";
import { JuryPanel } from "@/features/landing/JuryPanel";
import { useAuth } from "@/shared/lib/auth";
import { AdminSidebar } from "./AdminSidebar";
import { AppHeader } from "./AppHeader";
import { BottomNav } from "./BottomNav";
import { PageContainer } from "./PageContainer";
import { CANDIDATE_BOTTOM, EMPLOYER_BOTTOM } from "./shell-meta";

export { ThemeToggle } from "./AppHeader";

/** Счётчик «Приглашения» в шапке (если API ответил). Запрос только для своей роли. */
function useOfferCounts(variant: "top" | "side"): Record<string, number | undefined> {
  const { role } = useAuth();
  const employer = useListOffersOffersGet(undefined, { query: { enabled: variant === "top" && role === "employer", retry: false } });
  const candidate = useMyOffersCandidatesMeOffersGet(undefined, { query: { enabled: variant === "top" && role === "candidate", retry: false } });
  const interests = useMyInterestsCandidatesMeInterestsGet({ query: { enabled: variant === "top" && role === "candidate", retry: false } });
  const interestCount = interests.data?.status === 200 ? interests.data.data.companies : 0;
  return {
    "/employer/offers": offerCount(employer.data),
    // «Интересы» и «Отклики» — фильтр внутри «Приглашений», бейдж общий (E39-25).
    "/me/offers": positive((offerCount(candidate.data) ?? 0) + (interestCount > 0 ? interestCount : 0)),
  };
}

const positive = (n: number | undefined) => (n && n > 0 ? n : undefined);

/** Число приглашений для бейджа: свои отклики кандидата не считаем, ноль не показываем. */
export function offerCount(res?: { status: number; data: unknown }): number | undefined {
  if (res?.status !== 200 || !Array.isArray(res.data)) return undefined;
  return positive(res.data.filter((o) => (o as { initiator?: string }).initiator !== "candidate").length);
}

/**
 * Каркас по ролям (E19-5). Кабинеты кандидата и работодателя: шапка с меню на десктопе,
 * на ≤768 px ещё и нижняя панель (у работодателя — с E38-8); админка — боковая панель. `banner` — над страницей
 * (у кандидата — баннер пути «опрос → тест», E35-2a).
 */
export function Shell({ nav, variant, banner }: { nav: NavItem[]; variant: "top" | "side"; banner?: ReactNode }) {
  const { role } = useAuth();
  const counts = useOfferCounts(variant);
  // Нижняя панель на телефоне — у кандидата и работодателя (макеты v2: `.tb` на 4 пункта).
  const bottom = variant === "top" && (role === "candidate" || role === "employer");
  return (
    <div className={cn("min-h-dvh overflow-x-clip bg-page text-ink", variant === "side" && "md:grid md:grid-cols-[220px_1fr]")}>
      {variant === "side" && <AdminSidebar nav={nav} />}
      <div className="flex min-h-dvh min-w-0 flex-col">
        <AppHeader nav={nav} counts={counts} withTabs={variant === "top"} />
        {/* Поля задают сами страницы (p-4 md:p-6), поэтому контейнер без своих полей. */}
        <PageContainer className={cn("flex-1 px-0 md:px-0 lg:px-0", bottom && "pb-20 md:pb-0")} as="main">
          {banner}
          <Outlet />
        </PageContainer>
        <JuryPanel />
        {bottom && <BottomNav items={role === "candidate" ? CANDIDATE_BOTTOM : EMPLOYER_BOTTOM} all={nav} counts={counts} />}
      </div>
    </div>
  );
}
