import { cn, ErrorState } from "@fsp/ui";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "@/api/mutator";
import { errorView, T } from "./text";

/** Общая колонка страниц теста. */
export function Page({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return <div className={cn("mx-auto flex w-full flex-col gap-4", wide ? "max-w-5xl" : "max-w-3xl")}>{children}</div>;
}

/** Ошибка действия (кулдаун, email, согласия…) строкой с действием. */
export function ErrorLine({ error, ...rest }: { error: unknown; "data-testid"?: string }) {
  const v = errorView(error);
  return (
    <p role="alert" data-code={v.code} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-error-bg px-3 py-2 text-14 text-error" {...rest}>
      <span>{v.text}</span>
      {v.link && (
        <Link to={v.link.to} className="font-semibold underline">
          {v.link.label}
        </Link>
      )}
    </p>
  );
}

/** Ошибка загрузки страницы: 404 без «Повторить». */
export function LoadError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const v = errorView(error);
  const notFound = v.code === "not_found" || v.text === T.notFoundTitle;
  return (
    <div data-testid="assessment-error" data-code={v.code}>
      <ErrorState
        title={notFound ? T.notFoundTitle : T.errorTitle}
        description={notFound ? T.notFoundText : v.text}
        onRetry={notFound ? undefined : onRetry}
        action={
          v.link ? (
            <Link to={v.link.to} className="self-center text-14 font-semibold underline">
              {v.link.label}
            </Link>
          ) : undefined
        }
      />
    </div>
  );
}

/** Повторять только сбои сервера и сети: 4xx (404 чужой попытки, 409) повтор не лечит. */
export const retryServerOnly = (count: number, e: unknown): boolean => count < 1 && !(e instanceof ApiError && e.status < 500);
