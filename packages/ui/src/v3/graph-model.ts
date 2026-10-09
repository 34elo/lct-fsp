/* Модель EvidenceGraph (E39-14): раскладка, фильтры, подписи без наложений, вписывание в экран. Чистые функции без DOM. */

export interface EvidenceGraphNode {
  id: string;
  /** `skill`, факты (`fsp_result`, `repo`, `test`, `interview`, `experience`), `competition`, `team`; `candidate` не рисуется. */
  type: string;
  label: string;
  level?: number | null;
  /** Доверие 0–1. */
  confidence?: number | null;
  date?: string | null;
  verified?: boolean | null;
  derived_from?: string | null;
  /** Навык требуется вакансией, но у кандидата его нет. */
  ghost?: boolean | null;
  /** Тип навыка: fundamental | hard | thinking | business | soft | experience. */
  skill_type?: string | null;
}

export interface EvidenceGraphEdge {
  from: string;
  to: string;
  /** `confirms`, `parent`, `adjacent`, `at`, `member_of`; `has_fact` и `owns` идут от кандидата и не рисуются. */
  type: string;
  strength?: number | null;
  weight?: number | null;
}

export interface EvidenceGraphData {
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  highlight?: { requirement: string; path: string[] }[] | null;
}

export type NodeKind = "skill" | "fact" | "group";

export interface LaidNode {
  node: EvidenceGraphNode;
  kind: NodeKind;
  x: number;
  y: number;
  r: number;
  /** Навык с хотя бы одним фактом-подтверждением. */
  confirmed: boolean;
  /** На подсвеченном пути (требование вакансии). */
  hot: boolean;
  /** Тип навыка или `other`; у фактов — null. */
  skillType: string | null;
}

export interface GraphLayout {
  nodes: LaidNode[];
  byId: Map<string, LaidNode>;
  edges: EvidenceGraphEdge[];
  /** id → соседние id (в обе стороны). */
  neighbors: Map<string, Set<string>>;
  hotPairs: Set<string>;
  /** Типы навыков в порядке первого появления. */
  skillTypes: string[];
}

export interface GraphFilters {
  /** Пусто — все типы. */
  types: ReadonlySet<string>;
  onlyConfirmed: boolean;
}

export interface View {
  x: number;
  y: number;
  k: number;
}

export const OTHER_TYPE = "other";
export const MIN_K = 0.1;
export const MAX_K = 6;
/** Ниже этого масштаба подписи скрыты (кроме выбранного узла). */
export const LABEL_MIN_K = 0.15;
export const LABEL_MAX_CHARS = 28;

const SKILL_TYPE_ORDER = ["fundamental", "hard", "thinking", "business", "soft", "experience", OTHER_TYPE];
const DRAWN_EDGES = new Set(["confirms", "parent", "adjacent", "at", "member_of"]);
const GROUP_TYPES = new Set(["competition", "team"]);

export const pairKey = (a: string, b: string) => `${a}|${b}`;
export const clipLabel = (s: string, n = LABEL_MAX_CHARS) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Доверие 0–1 → точки ○○○○…●●●● (ml.md §3: 0.2 / 0.4 / 0.6 / 0.8). */
export function trustLevelOf(confidence?: number | null): 0 | 1 | 2 | 3 | 4 {
  const c = confidence ?? 0;
  if (c >= 0.8) return 4;
  if (c >= 0.6) return 3;
  if (c >= 0.4) return 2;
  if (c >= 0.2) return 1;
  return 0;
}

function kindOf(n: EvidenceGraphNode): NodeKind {
  if (n.type === "skill") return "skill";
  return GROUP_TYPES.has(n.type) ? "group" : "fact";
}

function radiusOf(n: EvidenceGraphNode, kind: NodeKind): number {
  if (kind === "group") return 6;
  if (kind === "fact") return 9;
  if (n.ghost) return 7;
  return 6 + Math.max(0, Math.min(1, n.confidence ?? 0)) * 10;
}

/**
 * Раскладка силами (Фрюхтерман — Рейнгольд), детерминированная: навыки по кругу, сгруппированные по типу,
 * факты внутри — у своих навыков. Считается один раз на данные; фильтры только скрывают узлы, и они не прыгают.
 */
export function layoutGraph(data: EvidenceGraphData, opts: { iterations?: number } = {}): GraphLayout {
  const src = data.nodes.filter((n) => n.type !== "candidate");
  const ids = new Set(src.map((n) => n.id));
  const edges = data.edges.filter((e) => DRAWN_EDGES.has(e.type) && ids.has(e.from) && ids.has(e.to) && e.from !== e.to);
  const confirmedIds = new Set(edges.filter((e) => e.type === "confirms").map((e) => e.to));

  const hotPairs = new Set<string>();
  const hotIds = new Set<string>();
  for (const h of data.highlight ?? []) {
    h.path.forEach((id, i) => {
      if (id.startsWith("s:")) hotIds.add(id);
      const next = h.path[i + 1];
      if (next) {
        hotPairs.add(pairKey(id, next));
        hotPairs.add(pairKey(next, id));
      }
    });
  }

  const neighbors = new Map<string, Set<string>>(src.map((n) => [n.id, new Set<string>()]));
  for (const e of edges) {
    neighbors.get(e.from)!.add(e.to);
    neighbors.get(e.to)!.add(e.from);
  }

  const typeOf = (n: EvidenceGraphNode) => n.skill_type || OTHER_TYPE;
  const rank = (t: string) => {
    const i = SKILL_TYPE_ORDER.indexOf(t);
    return i < 0 ? SKILL_TYPE_ORDER.length : i;
  };
  const skillsSorted = src
    .filter((n) => n.type === "skill")
    .map((n, i) => ({ n, i }))
    .sort((a, b) => rank(typeOf(a.n)) - rank(typeOf(b.n)) || typeOf(a.n).localeCompare(typeOf(b.n)) || (b.n.confidence ?? 0) - (a.n.confidence ?? 0) || a.i - b.i)
    .map(({ n }) => n);
  const skillTypes: string[] = [];
  for (const n of src) if (n.type === "skill" && !skillTypes.includes(typeOf(n))) skillTypes.push(typeOf(n));
  skillTypes.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));

  // Начальные позиции.
  const N = src.length;
  const index = new Map(src.map((n, i) => [n.id, i]));
  const px = new Float64Array(N);
  const py = new Float64Array(N);
  const rs = Math.max(140, (skillsSorted.length * 34) / (2 * Math.PI));
  const angle = new Map<string, number>();
  skillsSorted.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(1, skillsSorted.length) - Math.PI / 2;
    angle.set(n.id, a);
    const j = index.get(n.id)!;
    px[j] = Math.cos(a) * rs;
    py[j] = Math.sin(a) * rs;
  });
  const rest = src.filter((n) => n.type !== "skill");
  rest.sort((a, b) => (kindOf(a) === "group" ? 1 : 0) - (kindOf(b) === "group" ? 1 : 0));
  rest.forEach((n, i) => {
    let sx = 0;
    let sy = 0;
    for (const m of neighbors.get(n.id)!) {
      const a = angle.get(m);
      if (a !== undefined) {
        sx += Math.cos(a);
        sy += Math.sin(a);
      }
    }
    const a = sx === 0 && sy === 0 ? (2 * Math.PI * i) / Math.max(1, rest.length) : Math.atan2(sy, sx);
    angle.set(n.id, a);
    const rr = (kindOf(n) === "group" ? 0.75 : 0.45) * rs + (i % 5) * 9;
    const j = index.get(n.id)!;
    px[j] = Math.cos(a) * rr;
    py[j] = Math.sin(a) * rr;
  });

  const radius = src.map((n) => radiusOf(n, kindOf(n)));
  const pairs = edges.map((e) => [index.get(e.from)!, index.get(e.to)!, e.type === "confirms" ? 1 : 0.5] as const);
  const L = 60;
  const L2 = L * L;
  const CUT2 = (3 * L) ** 2;
  const iters = opts.iterations ?? (N > 150 ? 90 : 140);
  const dx = new Float64Array(N);
  const dy = new Float64Array(N);
  for (let it = 0; it < iters; it++) {
    const t = (rs / 5) * (1 - it / iters) + 1;
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        let vx = px[i] - px[j];
        let vy = py[i] - py[j];
        let d2 = vx * vx + vy * vy;
        if (d2 < 0.01) {
          vx = 0.1 * (((i * 7 + j) % 3) - 1) || 0.1;
          vy = 0.1;
          d2 = 0.02;
        }
        if (d2 > CUT2) continue; // отталкивание только у соседей: иначе граф из 200 узлов разлетается
        const f = L2 / d2;
        dx[i] += vx * f;
        dy[i] += vy * f;
        dx[j] -= vx * f;
        dy[j] -= vy * f;
      }
    }
    for (const [a, b, w] of pairs) {
      const vx = px[a] - px[b];
      const vy = py[a] - py[b];
      const d = Math.sqrt(vx * vx + vy * vy) || 0.1;
      const f = (d / L) * w;
      dx[a] -= vx * f;
      dy[a] -= vy * f;
      dx[b] += vx * f;
      dy[b] += vy * f;
    }
    for (let i = 0; i < N; i++) {
      dx[i] -= px[i] * 0.15;
      dy[i] -= py[i] * 0.15;
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]);
      if (d > 0) {
        const s = Math.min(d, t) / d;
        px[i] += dx[i] * s;
        py[i] += dy[i] * s;
      }
    }
  }
  // Узлы не пересекаются.
  for (let pass = 0; pass < 4; pass++) {
    for (let i = 0; i < N; i++) {
      for (let j = i + 1; j < N; j++) {
        const vx = px[i] - px[j];
        const vy = py[i] - py[j];
        const min = radius[i] + radius[j] + 8;
        const d2 = vx * vx + vy * vy;
        if (d2 >= min * min) continue;
        const d = Math.sqrt(d2) || 0.1;
        const push = (min - d) / 2;
        const ux = d2 === 0 ? 1 : vx / d;
        const uy = d2 === 0 ? 0 : vy / d;
        px[i] += ux * push;
        py[i] += uy * push;
        px[j] -= ux * push;
        py[j] -= uy * push;
      }
    }
  }

  const nodes: LaidNode[] = src.map((node, i) => {
    const kind = kindOf(node);
    return {
      node,
      kind,
      x: Math.round(px[i] * 10) / 10,
      y: Math.round(py[i] * 10) / 10,
      r: radius[i],
      confirmed: kind === "skill" && confirmedIds.has(node.id),
      hot: hotIds.has(node.id),
      skillType: kind === "skill" ? typeOf(node) : null,
    };
  });
  return { nodes, byId: new Map(nodes.map((n) => [n.node.id, n])), edges, neighbors, hotPairs, skillTypes };
}

/** Видимые узлы: навыки по типу и «только подтверждённые», факты — у видимых навыков, группы — у видимых фактов. */
export function visibleIds(layout: GraphLayout, f: GraphFilters): Set<string> {
  const active = f.types.size > 0 || f.onlyConfirmed;
  const out = new Set<string>();
  for (const n of layout.nodes) {
    if (n.kind !== "skill") continue;
    if (f.types.size > 0 && !f.types.has(n.skillType ?? OTHER_TYPE)) continue;
    if (f.onlyConfirmed && (!n.confirmed || n.node.ghost)) continue;
    out.add(n.node.id);
  }
  const hasSkillNeighbor = (id: string) => [...layout.neighbors.get(id)!].some((m) => layout.byId.get(m)!.kind === "skill");
  for (const n of layout.nodes) {
    if (n.kind !== "fact") continue;
    const nb = layout.neighbors.get(n.node.id)!;
    if ([...nb].some((m) => out.has(m)) || (!active && !hasSkillNeighbor(n.node.id))) out.add(n.node.id);
  }
  for (const n of layout.nodes) {
    if (n.kind === "group" && [...layout.neighbors.get(n.node.id)!].some((m) => out.has(m))) out.add(n.node.id);
  }
  return out;
}

/** Размер шрифта подписи на экране, px: растёт при приближении, мельчает при отдалении. */
export function labelFontPx(k: number): number {
  return Math.max(10, Math.min(15, 12 * Math.pow(k, 0.3)));
}

export interface LabelBox {
  id: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Прямоугольник подписи в экранных координатах при масштабе k (сдвиг вида не влияет на наложения). */
export function labelBox(n: LaidNode, k: number): LabelBox {
  const fs = labelFontPx(k);
  const w = clipLabel(n.node.label).length * fs * 0.58 + 4;
  const x0 = (n.x + n.r) * k + 4;
  const y0 = n.y * k - fs * 0.7;
  return { id: n.node.id, x0, y0, x1: x0 + w, y1: y0 + fs * 1.4 };
}

/**
 * Какие подписи показать при масштабе k, чтобы они не налезали: жадно по приоритету
 * (выбранный → подсвеченные → навыки по доверию → факты → группы), с сеткой для скорости.
 */
export function placeLabels(layout: GraphLayout, visible: ReadonlySet<string>, k: number, pinned: readonly string[] = []): Set<string> {
  const out = new Set<string>();
  const prio = (n: LaidNode) => (n.hot ? 0 : n.kind === "skill" ? (n.node.ghost ? 2 : 1) : n.kind === "fact" ? 3 : 4);
  const pinnedSet = new Set(pinned);
  const order = layout.nodes
    .filter((n) => visible.has(n.node.id))
    .filter((n) => k >= LABEL_MIN_K || pinnedSet.has(n.node.id))
    .sort((a, b) => Number(pinnedSet.has(b.node.id)) - Number(pinnedSet.has(a.node.id)) || prio(a) - prio(b) || (b.node.confidence ?? 0) - (a.node.confidence ?? 0));
  const CELL = 80;
  const grid = new Map<string, LabelBox[]>();
  const cells = (b: LabelBox) => {
    const res: string[] = [];
    for (let cx = Math.floor(b.x0 / CELL); cx <= Math.floor(b.x1 / CELL); cx++)
      for (let cy = Math.floor(b.y0 / CELL); cy <= Math.floor(b.y1 / CELL); cy++) res.push(`${cx}:${cy}`);
    return res;
  };
  for (const n of order) {
    const b = labelBox(n, k);
    const cs = cells(b);
    const hit = cs.some((c) => (grid.get(c) ?? []).some((o) => b.x0 < o.x1 && o.x0 < b.x1 && b.y0 < o.y1 && o.y0 < b.y1));
    if (hit && !pinnedSet.has(n.node.id)) continue;
    out.add(n.node.id);
    for (const c of cs) {
      const list = grid.get(c);
      if (list) list.push(b);
      else grid.set(c, [b]);
    }
  }
  return out;
}

/** Вид, при котором видимые узлы целиком помещаются в окно w×h с полями pad; справа ещё место под подписи. */
export function fitView(nodes: readonly LaidNode[], w: number, h: number, pad = 32, labelRoom = 0): View {
  if (nodes.length === 0) return { x: w / 2, y: h / 2, k: 1 };
  let x0 = Infinity;
  let y0 = Infinity;
  let x1 = -Infinity;
  let y1 = -Infinity;
  for (const n of nodes) {
    x0 = Math.min(x0, n.x - n.r);
    y0 = Math.min(y0, n.y - n.r);
    x1 = Math.max(x1, n.x + n.r);
    y1 = Math.max(y1, n.y + n.r);
  }
  const room = Math.min(labelRoom, w / 4);
  const k = clampK(Math.min((w - 2 * pad - room) / Math.max(1, x1 - x0), (h - 2 * pad) / Math.max(1, y1 - y0), 1.6));
  return { k, x: (w - room) / 2 - ((x0 + x1) / 2) * k, y: h / 2 - ((y0 + y1) / 2) * k };
}

export const clampK = (k: number) => Math.max(MIN_K, Math.min(MAX_K, k));

/** Масштаб с центром в экранной точке (px, py): точка под курсором или пальцами остаётся на месте. */
export function zoomAt(v: View, factor: number, px: number, py: number): View {
  const k = clampK(v.k * factor);
  const f = k / v.k;
  return { k, x: px - (px - v.x) * f, y: py - (py - v.y) * f };
}
