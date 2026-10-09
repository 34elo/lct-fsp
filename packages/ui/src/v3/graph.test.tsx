import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidenceGraph } from "./graph";
import { fitView, labelBox, layoutGraph, placeLabels, trustLevelOf, visibleIds, zoomAt, type EvidenceGraphData } from "./graph-model";

// jsdom не знает PointerEvent: без него fireEvent теряет pointerId, pointerType и координаты.
if (typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  window.PointerEvent = PointerEventPolyfill as unknown as typeof PointerEvent;
}

const data: EvidenceGraphData = {
  nodes: [
    { id: "cand", type: "candidate", label: "Backend #4821" },
    { id: "f:fsp:91", type: "fsp_result", label: "Кубок России, финал", date: "2025-04", verified: true },
    { id: "f:repo:7", type: "repo", label: "репозиторий · её кода 82%", date: "2026-08", verified: false },
    { id: "s:fastapi", type: "skill", label: "FastAPI", level: 3, confidence: 0.65, skill_type: "hard" },
    { id: "s:python", type: "skill", label: "Python", level: 2, confidence: 0.54, skill_type: "fundamental", derived_from: "s:fastapi" },
    { id: "s:teamwork", type: "skill", label: "Командная работа", level: 1, confidence: 0.3, skill_type: "soft" },
    { id: "s:django", type: "skill", label: "Django", level: 0, ghost: true, skill_type: "hard" },
  ],
  edges: [
    { from: "cand", to: "f:fsp:91", type: "has_fact" },
    { from: "f:repo:7", to: "s:fastapi", type: "confirms", strength: 0.5 },
    { from: "f:fsp:91", to: "s:python", type: "confirms", strength: 0.9 },
    { from: "cand", to: "s:teamwork", type: "owns", weight: 0.3 },
    { from: "s:fastapi", to: "s:python", type: "parent", weight: 0.6 },
    { from: "s:fastapi", to: "s:django", type: "adjacent", weight: 0.6 },
  ],
  highlight: [{ requirement: "fastapi", path: ["vac", "s:fastapi", "cand", "f:repo:7"] }],
};

/** Синтетический граф: n навыков, по факту на каждые 3 навыка, связи иерархии. */
function big(n: number): EvidenceGraphData {
  const types = ["fundamental", "hard", "thinking", "business", "soft", "experience"];
  const nodes: EvidenceGraphData["nodes"] = [];
  const edges: EvidenceGraphData["edges"] = [];
  for (let i = 0; i < n; i++) {
    nodes.push({ id: `s:${i}`, type: "skill", label: `Навык номер ${i}`, confidence: (i % 10) / 10, skill_type: types[i % types.length] });
    if (i % 3 === 0) {
      nodes.push({ id: `f:${i}`, type: "test", label: `Тест ${i}`, date: "2026-09" });
      edges.push({ from: `f:${i}`, to: `s:${i}`, type: "confirms", strength: 0.6 });
    }
    if (i > 0 && i % 4 === 0) edges.push({ from: `s:${i}`, to: `s:${i - 1}`, type: "parent" });
  }
  return { nodes, edges };
}

const nodeIds = () =>
  within(screen.getByTestId("egraph-nodes"))
    .queryAllByTestId(/^egraph-node-/)
    .map((el) => el.getAttribute("data-node"));

describe("модель графа", () => {
  it("кандидат и его рёбра не рисуются, навык подтверждён фактом, путь подсвечен", () => {
    const l = layoutGraph(data);
    expect(l.byId.has("cand")).toBe(false);
    expect(l.edges.map((e) => e.type).sort()).toEqual(["adjacent", "confirms", "confirms", "parent"]);
    expect(l.byId.get("s:fastapi")!.confirmed).toBe(true);
    expect(l.byId.get("s:teamwork")!.confirmed).toBe(false);
    expect(l.byId.get("s:fastapi")!.hot).toBe(true);
    expect(l.skillTypes).toEqual(["fundamental", "hard", "soft"]);
  });

  it("раскладка детерминирована и узлы не накладываются", () => {
    const a = layoutGraph(big(60));
    const b = layoutGraph(big(60));
    expect(a.nodes.map((n) => [n.x, n.y])).toEqual(b.nodes.map((n) => [n.x, n.y]));
    for (let i = 0; i < a.nodes.length; i++)
      for (let j = i + 1; j < a.nodes.length; j++) {
        const p = a.nodes[i]!;
        const q = a.nodes[j]!;
        expect(Math.hypot(p.x - q.x, p.y - q.y)).toBeGreaterThan(p.r + q.r);
      }
  });

  it("фильтры: тип навыка и «только подтверждённые»; факты — только у видимых навыков", () => {
    const l = layoutGraph(data);
    const all = visibleIds(l, { types: new Set(), onlyConfirmed: false });
    expect([...all].sort()).toEqual(["f:fsp:91", "f:repo:7", "s:django", "s:fastapi", "s:python", "s:teamwork"]);
    const hard = visibleIds(l, { types: new Set(["hard"]), onlyConfirmed: false });
    expect([...hard].sort()).toEqual(["f:repo:7", "s:django", "s:fastapi"]);
    const confirmed = visibleIds(l, { types: new Set(), onlyConfirmed: true });
    expect([...confirmed].sort()).toEqual(["f:fsp:91", "f:repo:7", "s:fastapi", "s:python"]);
  });

  it("подписи не налезают и скрываются при сильном отдалении", () => {
    const l = layoutGraph(big(200));
    const vis = visibleIds(l, { types: new Set(), onlyConfirmed: false });
    for (const k of [0.6, 1, 2.5]) {
      const shown = [...placeLabels(l, vis, k)].map((id) => labelBox(l.byId.get(id)!, k));
      for (let i = 0; i < shown.length; i++)
        for (let j = i + 1; j < shown.length; j++) {
          const a = shown[i]!;
          const b = shown[j]!;
          expect(a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1).toBe(false);
        }
    }
    expect(placeLabels(l, vis, 2.5).size).toBeGreaterThan(placeLabels(l, vis, 0.6).size);
    expect(placeLabels(l, vis, 0.1).size).toBe(0);
    expect([...placeLabels(l, vis, 0.1, ["s:5"])]).toEqual(["s:5"]);
  });

  it("вписать в экран и масштаб вокруг точки", () => {
    const l = layoutGraph(data);
    const v = fitView(l.nodes, 800, 480, 32);
    for (const n of l.nodes) {
      const sx = n.x * v.k + v.x;
      const sy = n.y * v.k + v.y;
      expect(sx).toBeGreaterThanOrEqual(31);
      expect(sx).toBeLessThanOrEqual(769);
      expect(sy).toBeGreaterThanOrEqual(31);
      expect(sy).toBeLessThanOrEqual(449);
    }
    const z = zoomAt({ x: 10, y: 20, k: 1 }, 2, 100, 100);
    expect(z.k).toBe(2);
    expect((100 - z.x) / z.k).toBeCloseTo(90); // точка под курсором осталась на месте
    expect(zoomAt({ x: 0, y: 0, k: 5 }, 10, 0, 0).k).toBe(6);
  });

  it("доверие → точки по порогам ml.md §3", () => {
    expect([0, 0.19, 0.2, 0.4, 0.6, 0.79, 0.8, 1].map(trustLevelOf)).toEqual([0, 0, 1, 2, 3, 3, 4, 4]);
  });
});

describe("EvidenceGraph", () => {
  it("рисует узлы, легенду, InfoTip и счётчик", () => {
    render(<EvidenceGraph data={data} />);
    expect(nodeIds()).toHaveLength(6);
    expect(screen.getByTestId("egraph-legend")).toHaveTextContent("подтверждение, толщина — сила");
    expect(screen.getByRole("button", { name: "Что это за граф" })).toBeInTheDocument();
    expect(screen.getByTestId("egraph-count")).toHaveTextContent("Навыков: 4 из 4");
    expect(screen.getAllByTestId("egraph-edge-confirms")).toHaveLength(2);
  });

  it("фильтр по типу навыка и «только подтверждённые»", () => {
    render(<EvidenceGraph data={data} />);
    fireEvent.click(screen.getByRole("button", { name: "Софт" }));
    expect(nodeIds()).toEqual(["s:teamwork"]);
    expect(screen.getByRole("button", { name: "Софт" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Хард" }));
    expect(nodeIds().sort()).toEqual(["f:repo:7", "s:django", "s:fastapi", "s:teamwork"]);
    fireEvent.click(screen.getByRole("button", { name: "Все типы" }));
    fireEvent.click(screen.getByRole("switch", { name: "Только подтверждённые" }));
    expect(nodeIds().sort()).toEqual(["f:fsp:91", "f:repo:7", "s:fastapi", "s:python"]);
    expect(screen.getByTestId("egraph-count")).toHaveTextContent("Навыков: 2 из 4");
    fireEvent.click(screen.getByRole("button", { name: "Софт" }));
    expect(nodeIds()).toEqual([]);
    expect(screen.getByText("Под фильтры не подходит ни один навык.")).toBeInTheDocument();
  });

  it("тап по навыку открывает карточку: доверие, источники, дата; повторный тап закрывает", () => {
    render(<EvidenceGraph data={data} renderSkillAction={(n) => <a href={`/me/skills/${n.id.slice(2)}`}>чем подтверждён</a>} />);
    const svg = screen.getByTestId("egraph-svg");
    const node = screen.getByTestId("egraph-node-s:fastapi").firstElementChild!;
    const tap = () => {
      fireEvent.pointerDown(node, { pointerId: 1, pointerType: "touch", clientX: 50, clientY: 50 });
      fireEvent.pointerUp(svg, { pointerId: 1, pointerType: "touch", clientX: 50, clientY: 50 });
    };
    tap();
    const card = screen.getByTestId("egraph-card");
    expect(card).toHaveTextContent("FastAPI");
    expect(card).toHaveTextContent("навык · Хард");
    expect(card).toHaveTextContent("Подтверждён · последнее 2026-08");
    expect(card).toHaveTextContent("65%");
    expect(within(card).getByText("репозиторий · её кода 82%")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "чем подтверждён" })).toHaveAttribute("href", "/me/skills/fastapi");
    tap();
    expect(screen.queryByTestId("egraph-card")).toBeNull();
  });

  it("наведение мышью показывает карточку факта", () => {
    render(<EvidenceGraph data={data} />);
    const node = screen.getByTestId("egraph-node-f:fsp:91").firstElementChild!;
    fireEvent.pointerMove(node, { pointerId: 1, pointerType: "mouse" });
    const card = screen.getByTestId("egraph-card");
    expect(card).toHaveTextContent("результат ФСП · 2025-04");
    expect(card).toHaveTextContent("Подтверждает: Python");
    expect(within(card).queryByRole("button", { name: "Закрыть карточку" })).toBeNull();
  });

  it("перетаскивание сдвигает, колесо и кнопки масштабируют, «вписать» возвращает", () => {
    render(<EvidenceGraph data={data} />);
    const svg = screen.getByTestId("egraph-svg");
    const vp = screen.getByTestId("egraph-viewport");
    const start = vp.getAttribute("transform");
    const k0 = Number(vp.dataset.k);
    fireEvent.pointerDown(svg, { pointerId: 1, pointerType: "mouse", button: 0, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(svg, { pointerId: 1, pointerType: "mouse", clientX: 160, clientY: 130 });
    fireEvent.pointerUp(svg, { pointerId: 1, pointerType: "mouse", clientX: 160, clientY: 130 });
    expect(vp.getAttribute("transform")).not.toBe(start);
    act(() => {
      svg.dispatchEvent(new WheelEvent("wheel", { deltaY: -200, clientX: 400, clientY: 240, bubbles: true, cancelable: true }));
    });
    expect(Number(vp.dataset.k)).toBeGreaterThan(k0);
    fireEvent.click(screen.getByRole("button", { name: "Отдалить" }));
    fireEvent.click(screen.getByTestId("egraph-fit"));
    expect(vp.getAttribute("transform")).toBe(start);
  });

  it("щипок двумя пальцами меняет масштаб", () => {
    render(<EvidenceGraph data={data} />);
    const svg = screen.getByTestId("egraph-svg");
    const vp = screen.getByTestId("egraph-viewport");
    const k0 = Number(vp.dataset.k);
    fireEvent.pointerDown(svg, { pointerId: 1, pointerType: "touch", clientX: 300, clientY: 200 });
    fireEvent.pointerDown(svg, { pointerId: 2, pointerType: "touch", clientX: 400, clientY: 200 });
    fireEvent.pointerMove(svg, { pointerId: 2, pointerType: "touch", clientX: 500, clientY: 200 });
    fireEvent.pointerUp(svg, { pointerId: 2, pointerType: "touch" });
    fireEvent.pointerUp(svg, { pointerId: 1, pointerType: "touch" });
    expect(Number(vp.dataset.k)).toBeCloseTo(k0 * 2, 2);
    expect(screen.queryByTestId("egraph-card")).toBeNull();
  });

  it("200 узлов: раскладка и отрисовка укладываются в бюджет", () => {
    const d = big(200);
    const t0 = performance.now();
    layoutGraph(d);
    const layoutMs = performance.now() - t0;
    render(<EvidenceGraph data={d} />);
    expect(nodeIds().length).toBe(d.nodes.length);
    expect(layoutMs).toBeLessThan(1500);
  });
});
