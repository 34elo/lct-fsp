import "./landing.css";

import { Final, Footer } from "./Closing";
import { FspBlock } from "./FspBlock";
import { Header } from "./Header";
import { Hero } from "./Hero";
import { How } from "./How";
import { Numbers } from "./Numbers";
import { Trust } from "./Trust";

/**
 * Лендинг `/`: шапка, hero, «Как это работает», «Доверие», ФСП, цифры,
 * финальный призыв, подвал. Тема — общий ThemeProvider. Цифры — `GET /public/stats`, без ответа блок скрыт;
 * остальное статично и вымышлено. Переходы T1–T6 и анимации A1–A10 — spec.html.
 */
export default function Landing() {
  return (
    <div className="lp min-h-screen bg-page text-ink">
      <Header />
      <main>
        <Hero />
        <How />
        <Trust />
        <FspBlock />
        <Numbers />
        <Final />
      </main>
      <Footer />
    </div>
  );
}
