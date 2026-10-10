import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import { useEffect, useId, useRef, useState, type PointerEvent as RPointerEvent } from "react";

import { cn } from "../lib/cn";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "../primitives/overlay";

/* ---------- Модель масштаба и сдвига (чистые функции, тесты без DOM) ---------- */

export type DiagramView = { scale: number; x: number; y: number };
export const DIAGRAM_VIEW0: DiagramView = { scale: 1, x: 0, y: 0 };
export const DIAGRAM_MIN_SCALE = 0.25;
export const DIAGRAM_MAX_SCALE = 8;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Масштаб с неподвижной точкой (px, py), отсчитанной от центра области: точка под курсором остаётся на месте. */
export function diagramZoomAt(v: DiagramView, factor: number, px: number, py: number): DiagramView {
  const scale = clamp(v.scale * factor, DIAGRAM_MIN_SCALE, DIAGRAM_MAX_SCALE);
  const k = scale / v.scale;
  return { scale, x: px - (px - v.x) * k, y: py - (py - v.y) * k };
}

/** Шаг колеса: прокрутка вверх (deltaY < 0) — приближение. */
export function diagramWheelFactor(deltaY: number): number {
  return Math.exp(-clamp(deltaY, -240, 240) * 0.0015);
}

/* ---------- Mermaid: ленивая загрузка, тема по токенам ---------- */

type MermaidApi = typeof import("mermaid").default;
let loader: Promise<MermaidApi> | null = null;

function loadMermaid(): Promise<MermaidApi> {
  loader ??= import("mermaid").then((m) => m.default);
  return loader;
}

function token(name: string, fallback: string): string {
  if (typeof document === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** Цвета схемы берём из токенов дизайн-системы: светлая и тёмная темы работают одинаково. */
function themeVars(): Record<string, string> {
  const ink = token("--ink", "#1b1c21");
  const card = token("--card", "#ffffff");
  const brand = token("--brand-fg", "#402fff");
  return {
    background: card,
    primaryColor: token("--tint-50", "#f4f3ff"),
    primaryTextColor: ink,
    primaryBorderColor: brand,
    secondaryColor: token("--tint-100", "#e6e4ff"),
    tertiaryColor: card,
    lineColor: token("--muted", "#5b5d66"),
    textColor: ink,
    mainBkg: token("--tint-50", "#f4f3ff"),
    nodeBorder: brand,
    clusterBkg: card,
    clusterBorder: token("--hairline", "#e1e1e5"),
    edgeLabelBackground: card,
    noteBkgColor: token("--tint-100", "#e6e4ff"),
    noteTextColor: ink,
    fontFamily: token("--font-sans", "system-ui, sans-serif"),
  };
}

type State = { kind: "loading" } | { kind: "ok"; svg: string } | { kind: "error"; message: string };

/** Рисует схему из Mermaid-текста. Ошибка синтаксиса — не падение: показываем исходный текст. */
function useMermaid(code: string, rid: string): State {
  const [state, setState] = useState<State>({ kind: "loading" });
  const vars = JSON.stringify(themeVars());
  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    loadMermaid()
      .then(async (mermaid) => {
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables: JSON.parse(vars) as Record<string, string> });
        const { svg } = await mermaid.render(rid, code);
        if (alive) setState({ kind: "ok", svg });
      })
      .catch((e: unknown) => {
        if (alive) setState({ kind: "error", message: e instanceof Error ? e.message : "Схема не построена" });
      });
    return () => {
      alive = false;
      // Mermaid оставляет временный узел в body при ошибке разбора.
      document.getElementById(`d${rid}`)?.remove();
    };
  }, [code, rid, vars]);
  return state;
}

/* ---------- Полноэкранный просмотр ---------- */

type Pt = { x: number; y: number };

function Viewer({ svg, title }: { svg: string; title: string }) {
  const [view, setView] = useState<DiagramView>(DIAGRAM_VIEW0);
  const area = useRef<HTMLDivElement>(null);
  const pts = useRef(new Map<number, Pt>());
  const pinch = useRef(0);

  /** Координаты клиента → от центра области (схема центрируется в ней). */
  const rel = (cx: number, cy: number): Pt => {
    const r = area.current?.getBoundingClientRect();
    return r ? { x: cx - r.left - r.width / 2, y: cy - r.top - r.height / 2 } : { x: 0, y: 0 };
  };

  // Колесо слушаем непассивно: preventDefault, чтобы не прокручивалась страница под окном.
  useEffect(() => {
    const el = area.current;
    if (!el) return;
    const on = (e: WheelEvent) => {
      e.preventDefault();
      const p = rel(e.clientX, e.clientY);
      setView((v) => diagramZoomAt(v, diagramWheelFactor(e.deltaY), p.x, p.y));
    };
    el.addEventListener("wheel", on, { passive: false });
    return () => el.removeEventListener("wheel", on);
  }, []);

  const down = (e: RPointerEvent) => {
    e.currentTarget.setPointerCapture?.(e.pointerId);
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    pinch.current = 0;
  };
  const move = (e: RPointerEvent) => {
    const prev = pts.current.get(e.pointerId);
    if (!prev) return;
    pts.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const list = [...pts.current.values()];
    const [a, b] = list;
    if (a && b) {
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch.current > 0 && dist > 0) {
        const p = rel((a.x + b.x) / 2, (a.y + b.y) / 2);
        setView((v) => diagramZoomAt(v, dist / pinch.current, p.x, p.y));
      }
      pinch.current = dist;
      return;
    }
    const dx = e.clientX - prev.x;
    const dy = e.clientY - prev.y;
    setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
  };
  const up = (e: RPointerEvent) => {
    pts.current.delete(e.pointerId);
    pinch.current = 0;
  };

  const btn = "inline-flex size-11 items-center justify-center rounded-md border border-hairline bg-card text-ink hover:bg-tint-50";
  return (
    <div>
      <div
        ref={area}
        role="img"
        aria-label={title}
        data-testid="diagram-viewer"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onDoubleClick={() => setView(DIAGRAM_VIEW0)}
        className="relative h-[60dvh] cursor-grab touch-none overflow-hidden rounded-lg border border-hairline bg-card select-none active:cursor-grabbing"
      >
        <div
          className="absolute top-1/2 left-1/2 w-max origin-center [&_svg]:h-auto [&_svg]:max-w-none"
          style={{ transform: `translate(-50%, -50%) translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
          data-testid="diagram-viewer-canvas"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
      <div className="mt-3 flex items-center gap-2" role="group" aria-label="Масштаб">
        <button type="button" className={btn} aria-label="Уменьшить" onClick={() => setView((v) => diagramZoomAt(v, 1 / 1.3, 0, 0))}>
          <Minus className="size-4" aria-hidden />
        </button>
        <button type="button" className={btn} aria-label="Увеличить" onClick={() => setView((v) => diagramZoomAt(v, 1.3, 0, 0))}>
          <Plus className="size-4" aria-hidden />
        </button>
        <button type="button" className={btn} aria-label="Сбросить масштаб" onClick={() => setView(DIAGRAM_VIEW0)}>
          <RotateCcw className="size-4" aria-hidden />
        </button>
        <span className="ml-auto font-mono text-12 text-muted" data-testid="diagram-scale">
          {Math.round(view.scale * 100)}%
        </span>
      </div>
    </div>
  );
}

/**
 * Схема из текста Mermaid: в карточке картинка (mermaid грузится лениво, при первом показе),
 * клик — полноэкранный просмотр с масштабом колесом и щипком и перетаскиванием. Тема — по токенам.
 * Ошибка в тексте схемы: показываем исходный текст, страница не падает.
 */
export function Diagram({ code, label = "Схема", className }: { code: string; label?: string; className?: string }) {
  const rid = "m" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const state = useMermaid(code, rid);
  const [open, setOpen] = useState(false);

  if (state.kind === "error") {
    return (
      <pre className={cn("my-2 overflow-x-auto rounded-lg bg-tint-50 p-3 font-mono text-13 leading-relaxed", className)} data-testid="diagram-error" title={state.message}>
        {code}
      </pre>
    );
  }
  if (state.kind === "loading") {
    return <div className={cn("my-2 h-32 animate-pulse rounded-lg bg-tint-50", className)} role="status" aria-label="Схема загружается" data-testid="diagram-loading" />;
  }
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`${label}: открыть на весь экран`}
        data-testid="diagram"
        className={cn("group relative my-2 block w-full cursor-zoom-in overflow-x-auto rounded-lg border border-hairline bg-card p-3 text-left hover:border-brand-mid", className)}
      >
        <div className="mx-auto w-fit max-w-full [&_svg]:h-auto [&_svg]:max-w-full" dangerouslySetInnerHTML={{ __html: state.svg }} />
        <span className="absolute top-2 right-2 inline-flex size-7 items-center justify-center rounded-md bg-card/90 text-muted group-hover:text-brand-fg" aria-hidden>
          <Maximize2 className="size-4" />
        </span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[min(72rem,calc(100%-2rem))]">
          <DialogTitle>{label}</DialogTitle>
          <DialogDescription>Колесо или щипок — масштаб, перетаскивание — сдвиг, двойной клик — сброс.</DialogDescription>
          <div className="mt-3">
            <Viewer svg={state.svg} title={label} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
