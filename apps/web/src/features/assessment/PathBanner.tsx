import { buttonVariants } from "@fsp/ui";
import { Link, useLocation } from "react-router-dom";

import { useHistoryAssessmentHistoryGet } from "@/api/endpoints/assessment/assessment";
import { PATH_START, pathStep } from "./model";
import { T } from "./text";

const HOME_PATH = "/me";

/**
 * Баннер главного пути кандидата (E35-2a): пока нет опроса или теста, на любом экране кандидата —
 * одна фраза и одна кнопка. На экранах самого опроса и теста не показывается; при ошибке API — тоже.
 * На Главной (`/me`, E38-1) тоже нет: там до теста весь экран — та же одна кнопка.
 */
export function PathBanner() {
  const { pathname } = useLocation();
  const onPath = pathname === PATH_START || pathname.startsWith(`${PATH_START}/`) || pathname === HOME_PATH;
  const hq = useHistoryAssessmentHistoryGet({ query: { enabled: !onPath, retry: false } });
  if (onPath || hq.data?.status !== 200) return null;
  const history = hq.data.data;
  // Неполный ответ (старый бэкенд, заглушка) — баннер не показываем, экран не роняем.
  if (!Array.isArray(history?.surveys) || !Array.isArray(history?.attempts)) return null;
  const step = pathStep(history);
  if (!step) return null;
  const copy = T.banner[step.kind];
  return (
    <div className="px-4 pt-4 md:px-6">
      <div
        role="region"
        aria-label={copy.action}
        className="mx-auto flex max-w-5xl flex-wrap items-center gap-3 rounded-xl border border-brand bg-tint-50 px-4 py-3"
        data-testid="path-banner"
        data-step={step.kind}
      >
        <p className="flex-1 text-14 font-medium">{copy.text}</p>
        <Link to={step.to} className={buttonVariants({ size: "sm" })} data-testid="path-banner-action">
          {copy.action}
        </Link>
      </div>
    </div>
  );
}
