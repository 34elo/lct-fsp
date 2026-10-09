import { Maximize2, X, ZoomIn, ZoomOut } from "lucide-react";
import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent as RPointerEvent,
  type ReactNode,
} from "react";

import { TrustDots } from "../brand";
import { cn } from "../lib/cn";
import { Button } from "../primitives/button";
import { Switch } from "../primitives/form";
import { InfoTip } from "./content";
import {
  clipLabel,
  fitView,
  labelFontPx,
  layoutGraph,
  pairKey,
  placeLabels,
  trustLevelOf,
  visibleIds,
  zoomAt,
  type EvidenceGraphData,
  type EvidenceGraphNode,
  type GraphLayout,
  type LaidNode,
  type View,
} from "./graph-model";

/* EvidenceGraph (E39-14): граф доказательств — масштаб колесом и щипком, перетаскивание, «вписать»,
   подписи без наложений, карточка узла при наведении и тапе, легенда, фильтры по типу навыка и «только подтверждённые». */

export const SKILL_TYPE_LABEL: Record<string, string> = {
  fundamental: "Фундамент",
  hard: "Хард",
  thinking: "Мышление",
  business: "Бизнес",
  soft: "Софт",
  experience: "Опыт",
  other: "Другое",
};

export const FACT_TYPE_LABEL: Record<string, string> = {
  fsp_result: "результат ФСП",
  repo: "репозиторий",
  test: "тест",
  interview: "интервью",
  experience: "опыт",
  competition: "соревнование",
  team: "команда",
};

const DEFAULT_INFO =
  "Навыки (круги) связаны с фактами (квадраты), которые их подтверждают: тестом, результатами ФСП, кодом. Чем толще линия, тем сильнее подтверждение.";

const FALLBACK = { w: 800, h: 480 };
const pct = (v?: number | null) => `${Math.round((v ?? 0) * 100)}%`;

export interface EvidenceGraphProps {
  data: EvidenceGraphData;
  /** Заголовок над графом; null — без заголовка. */
  title?: ReactNode;
  /** Текст InfoTip «что это за граф»; null — не показывать (когда пояснение уже есть у заголовка). */
  info?: ReactNode;
  /** Подписи типов навыков для фильтра. */
  typeLabels?: Record<string, string>;
  /** Действие в карточке навыка, например ссылка «чем подтверждён». */
  renderSkillAction?: (node: EvidenceGraphNode) => ReactNode;
  /** Начальное значение «только подтверждённые». */
  defaultOnlyConfirmed?: boolean;
  /** Скрыть переключатель «Только подтверждённые» (граф без фактов-подтверждений, например справочник навыков). */
  hideConfirmedFilter?: boolean;
  className?: string;
  "data-testid"?: string;
}

type Ptr = { x: number; y: number };

function nodeClass(n: LaidNode): string {
  if (n.kind === "group") return "fill-tint-100 stroke-muted";
  if (n.kind === "fact") return n.node.verified ? "fill-tint-200 stroke-brand-fg" : "fill-card stroke-ink";
  if (n.hot) return "fill-success stroke-success";
  if (n.node.ghost) return "fill-card stroke-muted";
  return n.confirmed ? "fill-brand stroke-brand-fg" : "fill-card stroke-brand-fg";
}

/** Рёбра и узлы не зависят от масштаба (толщина линий постоянна на экране), поэтому не перерисовываются при жестах. */
const Scene = memo(function Scene({ layout, visible, focus }: { layout: GraphLayout; visible: Set<string>; focus: Set<string> | null }) {
  return (
    <>
      <g data-testid="egraph-edges">
        {layout.edges.map((e, i) => {
          if (!visible.has(e.from) || !visible.has(e.to)) return null;
          const a = layout.byId.get(e.from)!;
          const b = layout.byId.get(e.to)!;
          const hot = layout.hotPairs.has(pairKey(e.from, e.to));
          const dim = focus && !(focus.has(e.from) && focus.has(e.to));
          const confirms = e.type === "confirms";
          return (
            <line
              key={i}
              data-testid={`egraph-edge-${e.type}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              vectorEffect="non-scaling-stroke"
              className={hot ? "stroke-success" : confirms ? "stroke-brand-fg" : "stroke-muted"}
              strokeOpacity={dim ? 0.12 : hot ? 1 : 0.55}
              strokeWidth={confirms ? 0.75 + (e.strength ?? 0.2) * 3 : 1.25}
              strokeDasharray={e.type === "adjacent" ? "6 4" : e.type === "parent" ? "1.5 3.5" : undefined}
            />
          );
        })}
      </g>
      <g data-testid="egraph-nodes">
        {layout.nodes.map((n) => {
          if (!visible.has(n.node.id)) return null;
          const dashed = (n.kind === "skill" && !n.confirmed && !n.hot) || n.node.ghost;
          const common = {
            className: nodeClass(n),
            vectorEffect: "non-scaling-stroke" as const,
            strokeWidth: n.hot ? 2.5 : 1.5,
            strokeDasharray: dashed ? "3 2.5" : undefined,
          };
          return (
            <g
              key={n.node.id}
              data-node={n.node.id}
              data-testid={`egraph-node-${n.node.id}`}
              data-kind={n.kind}
              opacity={focus && !focus.has(n.node.id) ? 0.25 : 1}
              className="cursor-pointer"
            >
              {n.kind === "skill" ? (
                <circle cx={n.x} cy={n.y} r={n.r} {...common} />
              ) : (
                <rect x={n.x - n.r} y={n.y - n.r} width={n.r * 2} height={n.r * 2} rx={n.kind === "fact" ? 3 : n.r} {...common} />
              )}
            </g>
          );
        })}
      </g>
    </>
  );
});

const Labels = memo(function Labels({ layout, shown, k, focus }: { layout: GraphLayout; shown: Set<string>; k: number; focus: Set<string> | null }) {
  const fs = labelFontPx(k) / k;
  return (
    <g data-testid="egraph-labels" className="pointer-events-none select-none" style={{ fontSize: fs }}>
      {[...shown].map((id) => {
        const n = layout.byId.get(id)!;
        return (
          <text
            key={id}
            x={n.x + n.r + 4 / k}
            y={n.y}
            dominantBaseline="central"
            opacity={focus && !focus.has(id) ? 0.25 : 1}
            className={cn("fill-ink stroke-card", n.kind === "skill" ? "font-semibold" : "", n.node.ghost && "fill-muted")}
            strokeWidth={3 / k}
            paintOrder="stroke"
          >
            {clipLabel(n.node.label)}
          </text>
        );
      })}
    </g>
  );
});

function NodeCard({
  layout,
  n,
  typeLabels,
  pinned,
  onClose,
  renderSkillAction,
}: {
  layout: GraphLayout;
  n: LaidNode;
  typeLabels: Record<string, string>;
  pinned: boolean;
  onClose: () => void;
  renderSkillAction?: (node: EvidenceGraphNode) => ReactNode;
}) {
  const { node } = n;
  const incoming = layout.edges.filter((e) => e.to === node.id && e.type === "confirms");
  const outgoing = layout.edges.filter((e) => e.from === node.id && e.type === "confirms");
  const dates = incoming.map((e) => layout.byId.get(e.from)?.node.date).filter((d): d is string => !!d).sort();
  const derived = node.derived_from ? layout.byId.get(node.derived_from)?.node.label ?? null : null;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold leading-snug text-ink">{node.label}</p>
          <p className="text-12 text-muted">
            {n.kind === "skill" ? `навык · ${typeLabels[n.skillType ?? "other"] ?? n.skillType}` : (FACT_TYPE_LABEL[node.type] ?? node.type)}
            {n.kind !== "skill" && node.date ? ` · ${node.date}` : ""}
          </p>
        </div>
        {pinned && (
          <button type="button" aria-label="Закрыть карточку" onClick={onClose} className="-m-2 inline-flex size-11 shrink-0 items-center justify-center rounded-lg text-muted hover:text-ink">
            <X className="size-4" aria-hidden />
          </button>
        )}
      </div>
      {n.kind === "skill" && node.ghost && <p className="text-13 text-muted">Не найден в профиле — требуется вакансией.</p>}
      {n.kind === "skill" && !node.ghost && (
        <>
          <div className="flex items-center gap-2 text-13 text-muted">
            <span>Доверие</span>
            <TrustDots level={trustLevelOf(node.confidence)} kind={n.confirmed ? "verified" : "claimed"} />
            <span className="font-mono">{pct(node.confidence)}</span>
          </div>
          <p className="text-13 text-muted">
            {n.confirmed ? "Подтверждён" : derived ? `Выведен из навыка ${derived}` : "Заявлен, без подтверждений"}
            {dates.length > 0 && ` · последнее ${dates[dates.length - 1]}`}
          </p>
        </>
      )}
      {incoming.length > 0 && (
        <div className="text-13">
          <p className="text-muted">Источники</p>
          <ul className="mt-1 flex flex-col gap-1">
            {incoming.slice(0, 5).map((e, i) => {
              const f = layout.byId.get(e.from)!.node;
              return (
                <li key={i} className="flex flex-wrap gap-x-2 text-ink">
                  <span>{f.label}</span>
                  <span className="text-muted">
                    {FACT_TYPE_LABEL[f.type] ?? f.type}
                    {f.date ? ` · ${f.date}` : ""} · сила <span className="font-mono">{pct(e.strength)}</span>
                  </span>
                </li>
              );
            })}
            {incoming.length > 5 && <li className="text-muted">и ещё {incoming.length - 5}</li>}
          </ul>
        </div>
      )}
      {n.kind === "fact" && (
        <div className="text-13">
          {node.verified != null && <p className="text-muted">{node.verified ? "Проверено" : "Не проверено"}</p>}
          {outgoing.length > 0 && (
            <p className="text-ink">
              <span className="text-muted">Подтверждает: </span>
              {outgoing.map((e) => layout.byId.get(e.to)!.node.label).join(", ")}
            </p>
          )}
        </div>
      )}
      {n.kind === "skill" && !node.ghost && renderSkillAction?.(node)}
    </div>
  );
}

function Legend() {
  const item = "inline-flex items-center gap-1.5";
  return (
    <ul data-testid="egraph-legend" aria-label="Легенда" className="flex flex-wrap gap-x-4 gap-y-1.5 text-12 text-muted">
      <li className={item}>
        <svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="5" className="fill-brand stroke-brand-fg" /></svg>
        навык подтверждён
      </li>
      <li className={item}>
        <svg width="12" height="12" aria-hidden><circle cx="6" cy="6" r="5" className="fill-card stroke-brand-fg" strokeDasharray="3 2" /></svg>
        заявлен
      </li>
      <li className={item}>
        <svg width="12" height="12" aria-hidden><rect x="1" y="1" width="10" height="10" rx="2" className="fill-tint-200 stroke-brand-fg" /></svg>
        факт (тест, ФСП, код)
      </li>
      <li className={item}>
        <svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" className="stroke-brand-fg" strokeWidth="2.5" /></svg>
        подтверждение, толщина — сила
      </li>
      <li className={item}>
        <svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" className="stroke-muted" strokeWidth="1.5" strokeDasharray="1.5 3.5" /></svg>
        входит в навык
      </li>
      <li className={item}>
        <svg width="22" height="8" aria-hidden><line x1="0" y1="4" x2="22" y2="4" className="stroke-muted" strokeWidth="1.5" strokeDasharray="6 4" /></svg>
        смежный навык
      </li>
    </ul>
  );
}

/** Интерактивный граф доказательств. Подходит и для 200+ узлов: раскладка считается один раз, жесты не перерисовывают сцену. */
export function EvidenceGraph({
  data,
  title = "Граф доказательств",
  info = DEFAULT_INFO,
  typeLabels = SKILL_TYPE_LABEL,
  renderSkillAction,
  defaultOnlyConfirmed = false,
  hideConfirmedFilter = false,
  className,
  "data-testid": testId = "egraph",
}: EvidenceGraphProps) {
  const layout = useMemo(() => layoutGraph(data), [data]);
  const [types, setTypes] = useState<ReadonlySet<string>>(() => new Set());
  const [onlyConfirmed, setOnlyConfirmed] = useState(defaultOnlyConfirmed);
  const visible = useMemo(() => visibleIds(layout, { types, onlyConfirmed }), [layout, types, onlyConfirmed]);

  const boxRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState(FALLBACK);
  const [view, setView] = useState<View>({ x: FALLBACK.w / 2, y: FALLBACK.h / 2, k: 1 });
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const read = () => {
      const w = el.clientWidth || FALLBACK.w;
      const h = el.clientHeight || FALLBACK.h;
      setSize((s) => (s.w === w && s.h === h ? s : { w, h }));
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const visibleNodes = useMemo(() => layout.nodes.filter((n) => visible.has(n.node.id)), [layout, visible]);
  const fit = useCallback(() => setView(fitView(visibleNodes, size.w, size.h, 24, 72)), [visibleNodes, size.w, size.h]);
  useEffect(fit, [fit]);

  useEffect(() => {
    if (selected && !visible.has(selected)) setSelected(null);
    if (hovered && !visible.has(hovered)) setHovered(null);
  }, [visible, selected, hovered]);

  // Колесо: нативный слушатель, чтобы отменить прокрутку страницы (у React он пассивный).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      setView((v) => zoomAt(v, Math.exp(-dy * 0.0015), e.clientX - r.left, e.clientY - r.top));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  const pointers = useRef(new Map<number, Ptr>());
  const gesture = useRef<{ start: Ptr; moved: boolean; node: string | null } | null>(null);
  const local = (e: RPointerEvent): Ptr => {
    const r = svgRef.current!.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const nodeAt = (t: EventTarget | null) => (t instanceof Element ? t.closest("[data-node]")?.getAttribute("data-node") ?? null : null);

  const onPointerDown = (e: RPointerEvent<SVGSVGElement>) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const p = local(e);
    pointers.current.set(e.pointerId, p);
    if (pointers.current.size === 1) gesture.current = { start: p, moved: false, node: nodeAt(e.target) };
    else if (gesture.current) gesture.current.moved = true; // второй палец — щипок, не тап
  };
  const onPointerMove = (e: RPointerEvent<SVGSVGElement>) => {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) {
      if (e.pointerType === "mouse") setHovered(nodeAt(e.target));
      return;
    }
    const p = local(e);
    const ps = [...pointers.current.entries()];
    pointers.current.set(e.pointerId, p);
    const g = gesture.current;
    if (ps.length === 1) {
      if (g && !g.moved && Math.hypot(p.x - g.start.x, p.y - g.start.y) > 4) g.moved = true;
      if (g?.moved) setView((v) => ({ ...v, x: v.x + p.x - prev.x, y: v.y + p.y - prev.y }));
    } else if (ps.length >= 2) {
      const other = ps.find(([id]) => id !== e.pointerId)![1];
      const d0 = Math.hypot(prev.x - other.x, prev.y - other.y) || 1;
      const d1 = Math.hypot(p.x - other.x, p.y - other.y) || 1;
      const m0 = { x: (prev.x + other.x) / 2, y: (prev.y + other.y) / 2 };
      const m1 = { x: (p.x + other.x) / 2, y: (p.y + other.y) / 2 };
      setView((v) => {
        const z = zoomAt(v, d1 / d0, m0.x, m0.y);
        return { ...z, x: z.x + m1.x - m0.x, y: z.y + m1.y - m0.y };
      });
    }
  };
  const onPointerUp = (e: RPointerEvent<SVGSVGElement>) => {
    if (!pointers.current.delete(e.pointerId)) return;
    const g = gesture.current;
    if (pointers.current.size === 0) {
      gesture.current = null;
      if (g && !g.moved) setSelected((s) => (g.node && s !== g.node ? g.node : null));
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = 40;
    const c = { x: size.w / 2, y: size.h / 2 };
    const act: Record<string, () => void> = {
      "+": () => setView((v) => zoomAt(v, 1.25, c.x, c.y)),
      "=": () => setView((v) => zoomAt(v, 1.25, c.x, c.y)),
      "-": () => setView((v) => zoomAt(v, 0.8, c.x, c.y)),
      "0": fit,
      ArrowLeft: () => setView((v) => ({ ...v, x: v.x + step })),
      ArrowRight: () => setView((v) => ({ ...v, x: v.x - step })),
      ArrowUp: () => setView((v) => ({ ...v, y: v.y + step })),
      ArrowDown: () => setView((v) => ({ ...v, y: v.y - step })),
      Escape: () => setSelected(null),
    };
    const f = act[e.key];
    if (f && e.target === e.currentTarget) {
      e.preventDefault();
      f();
    }
  };

  const active = selected ?? hovered;
  const focus = useMemo(() => {
    if (!active) return null;
    return new Set([active, ...(layout.neighbors.get(active) ?? [])]);
  }, [active, layout]);
  const kStep = Math.round(view.k * 50) / 50; // подписи пересчитываются шагами масштаба, а не на каждый кадр
  const shown = useMemo(() => placeLabels(layout, visible, kStep, active ? [active] : []), [layout, visible, kStep, active]);

  const card = active ? layout.byId.get(active) : undefined;
  const narrow = size.w < 520;
  let cardStyle: CSSProperties | undefined;
  if (card && !narrow) {
    // Карточка под узлом или над ним, чтобы не закрывать его подпись справа.
    const sx = card.x * view.k + view.x;
    const sy = card.y * view.k + view.y;
    const r = card.r * view.k;
    const W = 288;
    const left = Math.max(8, Math.min(size.w - W - 8, sx - 24));
    const top = Math.max(8, sy + r + 10);
    const bottom = Math.max(8, size.h - sy + r + 10);
    cardStyle = sy < size.h / 2 ? { left, width: W, top, maxHeight: Math.max(120, size.h - top - 8) } : { left, width: W, bottom, maxHeight: Math.max(120, size.h - bottom - 8) };
  }

  const skillTotal = layout.nodes.filter((n) => n.kind === "skill").length;
  const skillShown = visibleNodes.filter((n) => n.kind === "skill").length;
  const toggleType = (t: string) =>
    setTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  return (
    <div data-testid={testId} className={cn("flex flex-col gap-3", className)}>
      {(title != null || info != null) && (
        <div className="flex items-center gap-1.5">
          {title != null && (typeof title === "string" ? <h3 className="text-16 font-semibold text-ink">{title}</h3> : title)}
          {info != null && (
            <InfoTip title="Что это за граф" label="Что это за граф" data-testid={`${testId}-info`}>
              {info}
            </InfoTip>
          )}
        </div>
      )}

      <div role="group" aria-label="Фильтры графа" data-testid={`${testId}-filters`} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        {layout.skillTypes.length > 1 ? (
          <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Тип навыка">
            <button
              type="button"
              aria-pressed={types.size === 0}
              onClick={() => setTypes(new Set())}
              data-testid={`${testId}-type-all`}
              className={chip(types.size === 0)}
            >
              Все типы
            </button>
            {layout.skillTypes.map((t) => (
              <button key={t} type="button" aria-pressed={types.has(t)} onClick={() => toggleType(t)} data-testid={`${testId}-type-${t}`} className={chip(types.has(t))}>
                {typeLabels[t] ?? t}
              </button>
            ))}
          </div>
        ) : (
          <span />
        )}
        {!hideConfirmedFilter && (
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 whitespace-nowrap text-14 text-ink">
            <Switch checked={onlyConfirmed} onCheckedChange={setOnlyConfirmed} data-testid={`${testId}-confirmed`} aria-label="Только подтверждённые" />
            Только подтверждённые
          </label>
        )}
      </div>

      <div
        ref={boxRef}
        tabIndex={0}
        role="group"
        aria-roledescription="граф"
        aria-label={`Граф: навыков ${skillShown} из ${skillTotal}. Колесо или щипок — масштаб, перетаскивание — сдвиг, плюс и минус — масштаб, 0 — вписать.`}
        onKeyDown={onKeyDown}
        className="relative h-[420px] overflow-hidden rounded-xl border border-hairline bg-page outline-none focus-visible:ring-2 focus-visible:ring-brand md:h-[520px]"
      >
        <svg
          ref={svgRef}
          data-testid={`${testId}-svg`}
          width="100%"
          height="100%"
          aria-hidden
          className="block cursor-grab touch-none select-none active:cursor-grabbing"
          style={{ fontFamily: "var(--font-sans)" }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={(e) => e.pointerType === "mouse" && !pointers.current.size && setHovered(null)}
        >
          <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`} data-testid={`${testId}-viewport`} data-k={view.k.toFixed(3)}>
            <Scene layout={layout} visible={visible} focus={focus} />
            <Labels layout={layout} shown={shown} k={view.k} focus={focus} />
          </g>
        </svg>

        {visibleNodes.length === 0 && (
          <p className="absolute inset-0 flex items-center justify-center p-6 text-center text-14 text-muted">Под фильтры не подходит ни один навык.</p>
        )}

        <div className="absolute right-2 top-2 flex flex-col gap-1 rounded-lg border border-hairline bg-card p-1 shadow-card">
          <Button variant="ghost" size="icon" aria-label="Приблизить" onClick={() => setView((v) => zoomAt(v, 1.25, size.w / 2, size.h / 2))}>
            <ZoomIn className="size-4" aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Отдалить" onClick={() => setView((v) => zoomAt(v, 0.8, size.w / 2, size.h / 2))}>
            <ZoomOut className="size-4" aria-hidden />
          </Button>
          <Button variant="ghost" size="icon" aria-label="Вписать в экран" data-testid={`${testId}-fit`} onClick={fit}>
            <Maximize2 className="size-4" aria-hidden />
          </Button>
        </div>

        {card && (
          <div
            data-testid={`${testId}-card`}
            role="dialog"
            aria-label={card.node.label}
            style={cardStyle}
            onPointerEnter={() => selected === null && setHovered(card.node.id)}
            className={cn(
              "absolute z-10 rounded-lg border border-hairline bg-card p-3 shadow-card",
              narrow ? "inset-x-2 bottom-2 max-h-[60%] overflow-y-auto" : "overflow-y-auto",
            )}
          >
            <NodeCard layout={layout} n={card} typeLabels={typeLabels} pinned={selected !== null} onClose={() => setSelected(null)} renderSkillAction={renderSkillAction} />
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
        <Legend />
        <p className="whitespace-nowrap text-12 text-muted" data-testid={`${testId}-count`}>
          Навыков: {skillShown} из {skillTotal}
        </p>
      </div>
    </div>
  );
}

function chip(on: boolean) {
  return cn(
    "inline-flex h-11 items-center rounded-full border px-3 text-13 font-semibold transition-colors sm:h-9",
    on ? "border-brand bg-brand text-on-brand" : "border-hairline bg-card text-ink hover:bg-tint-50",
  );
}
