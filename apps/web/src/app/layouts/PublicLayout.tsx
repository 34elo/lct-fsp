import { Link, Outlet } from "react-router-dom";

import { useAuth } from "@/shared/lib/auth";
import { Logo } from "@/shared/brand";
import { ThemeToggle } from "./Shell";

export default function PublicLayout() {
  const { status } = useAuth();
  return (
    <div className="min-h-dvh bg-page text-ink">
      <header className="flex items-center gap-3 border-b border-hairline bg-card px-4 py-3">
        <Link to="/" aria-label="На главную">
          <Logo />
        </Link>
        <div className="ml-auto flex items-center gap-3">
          <ThemeToggle />
          {status === "anonymous" && (
            <Link to="/login" className="font-semibold text-brand-fg">
              Войти
            </Link>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl p-4 md:p-6">
        <Outlet />
      </main>
    </div>
  );
}
