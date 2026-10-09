import { cn } from "@fsp/ui";
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ElementType, type HTMLAttributes, type RefObject } from "react";

/* Движение лендинга (spec.html): появление блоков (A3), счётчики (A8), плавная прокрутка (T4).
   Везде учитывается prefers-reduced-motion: итоговое состояние сразу, без анимации. */

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const hasObserver = () => typeof IntersectionObserver === "function";

/** Элемент стал виден на `threshold` своей площади: один раз. Без IntersectionObserver или при reduced-motion — сразу. */
export function useInView<T extends Element>(threshold: number, rootMargin = "0px"): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [seen, setSeen] = useState(() => !hasObserver() || prefersReducedMotion());
  useEffect(() => {
    const el = ref.current;
    if (seen || !el || !hasObserver()) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setSeen(true);
          io.disconnect();
        }
      },
      { threshold, rootMargin },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [seen, threshold, rootMargin]);
  return [ref, seen];
}

type RevealProps<E extends ElementType> = { as?: E; delay?: number } & Omit<HTMLAttributes<HTMLElement>, "as">;

/** A3: opacity 0 → 1 со сдвигом 16 px, когда видно 15 % блока. `delay` — каскад, мс. Дети читают `[data-in=true]` (A6, A7). */
export function Reveal<E extends ElementType = "div">({ as, delay = 0, className, style, ...p }: RevealProps<E>) {
  const Tag = (as ?? "div") as ElementType;
  const [ref, seen] = useInView<HTMLElement>(0.15, "0px 0px -6% 0px");
  return (
    <Tag
      ref={ref}
      data-in={seen}
      className={cn("lp-rv", className)}
      style={{ "--d": `${delay}ms`, ...style } as CSSProperties}
      {...p}
    />
  );
}

const easeOutCubic = (p: number) => 1 - (1 - p) ** 3;

/** Число с неразрывными пробелами между разрядами: «1 248». */
export function formatCount(n: number): string {
  return new Intl.NumberFormat("ru-RU").format(n).replace(/\s/g, " ");
}

/** A8: досчитывает от 0 до `value` за 1400 мс (easeOutCubic), когда видно 40 % счётчика. */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const [ref, seen] = useInView<HTMLElement>(0.4);
  const instant = !hasObserver() || prefersReducedMotion();
  const [shown, setShown] = useState(instant ? value : 0);
  useEffect(() => {
    if (!seen) return;
    if (instant) {
      setShown(value);
      return;
    }
    let raf = 0;
    let t0: number | null = null;
    const step = (ts: number) => {
      t0 ??= ts;
      const p = Math.min(1, (ts - t0) / 1400);
      setShown(Math.round(value * easeOutCubic(p)));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [seen, value, instant]);
  return (
    <b ref={ref} aria-label={formatCount(value)} className={className}>
      <span aria-hidden="true">{formatCount(shown)}</span>
    </b>
  );
}

const easeInOut = (p: number) => (p < 0.5 ? 4 * p ** 3 : 1 - (-2 * p + 2) ** 3 / 2);

/** T4: плавная прокрутка к блоку страницы за 500 мс ease-in-out; при reduced-motion — мгновенно. */
export function scrollToId(id: string): void {
  const el = document.getElementById(id);
  if (!el) return;
  const header = document.querySelector<HTMLElement>("[data-lp-header]");
  const target = Math.max(0, el.getBoundingClientRect().top + window.scrollY - (header?.offsetHeight ?? 64));
  el.focus({ preventScroll: true });
  if (prefersReducedMotion()) {
    window.scrollTo(0, target);
    return;
  }
  const from = window.scrollY;
  let t0: number | null = null;
  const step = (ts: number) => {
    t0 ??= ts;
    const p = Math.min(1, (ts - t0) / 500);
    window.scrollTo(0, from + (target - from) * easeInOut(p));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/** Якорь страницы: клик плавно прокручивает к блоку, адрес не меняется. */
export function onAnchorClick(id: string) {
  return (e: { preventDefault: () => void }) => {
    e.preventDefault();
    scrollToId(id);
  };
}

/** Замер после отрисовки, при смене размера окна и загрузке шрифтов (подложка вкладки). */
export function useLayoutMeasure(measure: () => void, deps: unknown[]): void {
  useLayoutEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    void document.fonts?.ready?.then(measure);
    return () => window.removeEventListener("resize", measure);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
