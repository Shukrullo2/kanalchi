/**
 * The canvas behind the map.
 *
 * React owns the filters and the panel; this owns the pixels. It runs the force
 * layout, paints on every tick, hit-tests with a quadtree, and handles pan,
 * zoom and node dragging with d3's behaviours. It is a class rather than a
 * component because a force simulation is long-lived mutable state that a
 * render cycle should not be re-creating.
 *
 * Two decisions worth naming. Rendering is canvas, not SVG, because a season
 * of a busy channel is two thousand dots and five thousand lines, and SVG
 * stops being interactive well before that. And the simulation is pre-run
 * synchronously when a graph arrives, so the map appears settled instead of
 * unfolding for three seconds every time a filter changes.
 */

import { drag } from "d3-drag";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation } from "d3-force";
import { quadtree, type Quadtree } from "d3-quadtree";
import { pointer, select } from "d3-selection";
import "d3-transition";
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
import { tierOf } from "@/lib/dimensions";
import type { GLink, GNode, Graph, Mode } from "@/lib/graph";

export type Palette = {
  theme: string;
  entity: string;
  meta: string;
  post: string;
  isolate: string;
  edge: string;
  edgeFocus: string;
  edgePost: string;
  halo: string;
  font: string;
};

/** Colours come from the page's own variables, so light mode and any tenant theme just work. */
export function readPalette(): Palette {
  const cs = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  return {
    theme: v("--primary", "#f5c518"),
    entity: v("--accent", "#56c6f0"),
    meta: v("--muted-foreground", "#93a4c8"),
    post: v("--foreground", "#f6f3ea"),
    isolate: v("--muted-foreground", "#93a4c8"),
    edge: v("--border-strong", "#33477a"),
    edgeFocus: v("--foreground", "#f6f3ea"),
    edgePost: v("--primary", "#f5c518"),
    halo: v("--background", "#0e1830"),
    font: getComputedStyle(document.body).fontFamily || "sans-serif",
  };
}

export type EngineEvents = {
  onHover: (node: GNode | null, x: number, y: number) => void;
  onClick: (node: GNode | null) => void;
  onDoubleClick: (node: GNode) => void;
  labelOf: (node: GNode) => string;
};

const LABELLED_HUBS = 28;

export class GraphEngine {
  private ctx: CanvasRenderingContext2D;
  private nodes: GNode[] = [];
  private links: GLink[] = [];
  private mode: Mode = "constellation";
  private wmax = 1;
  private sim: Simulation<GNode, GLink> | null = null;
  private transform: ZoomTransform = zoomIdentity;
  private hovered: GNode | null = null;
  private selected: GNode | null = null;
  private quad: Quadtree<GNode> | null = null;
  private W = 0;
  private H = 0;
  private dpr = 1;
  private autoFit = true;
  private ticks = 0;
  private palette: Palette;
  private zoomer: ZoomBehavior<HTMLCanvasElement, unknown>;
  private prev = new Map<string, [number, number]>();
  private themeWatch: MutationObserver;
  private sizeWatch: ResizeObserver;

  constructor(
    private canvas: HTMLCanvasElement,
    private events: EngineEvents,
  ) {
    this.ctx = canvas.getContext("2d")!;
    // For tests and the console: the engine behind a canvas.
    (canvas as HTMLCanvasElement & { __engine?: GraphEngine }).__engine = this;
    this.palette = readPalette();
    this.themeWatch = new MutationObserver(() => {
      this.palette = readPalette();
      this.paint();
    });
    this.themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    this.sizeWatch = new ResizeObserver(() => this.resize());
    this.sizeWatch.observe(canvas.parentElement ?? canvas);

    this.zoomer = zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.12, 9])
      .filter((e: MouseEvent | WheelEvent | TouchEvent) => {
        if ("button" in e && e.button) return false;
        if (e.ctrlKey && e.type !== "wheel") return false;
        if (e.type === "mousedown" || e.type === "touchstart") {
          const [x, y] = pointer(e, canvas);
          return !this.hit(x, y);
        }
        return true;
      })
      .on("zoom", (e) => {
        if (e.sourceEvent) this.autoFit = false;
        this.transform = e.transform;
        this.paint();
      });
    const dragger = drag<HTMLCanvasElement, unknown, GNode>()
      .container(() => canvas)
      .subject((e) => this.hit(e.x, e.y) as GNode)
      .on("start", (e) => {
        if (!e.active) this.sim?.alphaTarget(0.3).restart();
        e.subject.fx = e.subject.x;
        e.subject.fy = e.subject.y;
        canvas.classList.add("dragging");
      })
      .on("drag", (e) => {
        e.subject.fx = (e.subject.fx ?? e.subject.x) + e.dx / this.transform.k;
        e.subject.fy = (e.subject.fy ?? e.subject.y) + e.dy / this.transform.k;
      })
      .on("end", (e) => {
        if (!e.active) this.sim?.alphaTarget(0);
        e.subject.fx = null;
        e.subject.fy = null;
        canvas.classList.remove("dragging");
      });
    select(canvas).call(dragger).call(this.zoomer).on("dblclick.zoom", null);

    canvas.addEventListener("mousemove", this.onMove);
    canvas.addEventListener("mouseleave", this.onLeave);
    canvas.addEventListener("click", this.onClick);
    canvas.addEventListener("dblclick", this.onDouble);
    this.resize();
  }

  destroy() {
    this.sim?.stop();
    this.themeWatch.disconnect();
    this.sizeWatch.disconnect();
    select(this.canvas).on(".zoom", null).on(".drag", null);
    this.canvas.removeEventListener("mousemove", this.onMove);
    this.canvas.removeEventListener("mouseleave", this.onLeave);
    this.canvas.removeEventListener("click", this.onClick);
    this.canvas.removeEventListener("dblclick", this.onDouble);
  }

  // --- data -----------------------------------------------------------------

  setGraph(graph: Graph, mode: Mode) {
    for (const n of this.nodes) this.prev.set(n.id, [n.x, n.y]);
    this.mode = mode;
    this.nodes = graph.nodes;
    this.links = graph.links;
    this.wmax = graph.wmax;
    for (const n of this.nodes) {
      const p = this.prev.get(n.id);
      if (p) {
        n.x = p[0];
        n.y = p[1];
      }
    }
    this.hovered = null;
    this.selected = this.selected ? (this.nodes.find((n) => n.id === this.selected!.id) ?? null) : null;
    this.sim?.stop();
    const sim = forceSimulation<GNode, GLink>(this.nodes);
    if (mode === "constellation") {
      sim
        .force("link", forceLink<GNode, GLink>(this.links).distance((l) => (l.kind === "tag" ? 26 : 34)).strength((l) => (l.kind === "tag" ? 0.45 : 0.7)))
        .force("charge", forceManyBody<GNode>().strength((n) => (n.kind === "tag" ? -140 : -9)).theta(0.9))
        .force("x", forceX<GNode>(0).strength((n) => (n.deg ? 0.015 : 0.06)))
        .force("y", forceY<GNode>(0).strength((n) => (n.deg ? 0.015 : 0.06)))
        .force("collide", forceCollide<GNode>((n) => n.r + 1.2).iterations(1));
    } else {
      const wmax = this.wmax;
      sim
        .force("link", forceLink<GNode, GLink>(this.links).distance((l) => 40 + 120 * (1 - l.w / wmax)).strength((l) => 0.15 + 0.5 * (l.w / wmax)))
        .force("charge", forceManyBody<GNode>().strength(-260))
        .force("center", forceCenter(0, 0).strength(0.05))
        .force("x", forceX<GNode>(0).strength(0.03))
        .force("y", forceY<GNode>(0).strength(0.035))
        .force("collide", forceCollide<GNode>((n) => n.r + 10));
    }
    sim.alphaDecay(mode === "constellation" ? 0.028 : 0.03).on("tick", () => {
      this.quad = null;
      if (this.autoFit && sim.alpha() > 0.04 && ++this.ticks % 6 === 0) this.fit(false);
      this.paint();
    });
    this.sim = sim;
    this.autoFit = true;
    this.ticks = 0;
    // Settle before the first frame, then let it breathe.
    sim.stop();
    sim.tick(Math.max(60, Math.min(160, Math.round(30000 / Math.max(1, this.nodes.length)))));
    this.quad = null;
    this.fit(false);
    this.paint();
    sim.alpha(0.35).restart();
  }

  setSelected(id: string | null) {
    this.selected = id ? (this.nodes.find((n) => n.id === id) ?? null) : null;
    this.paint();
  }

  // --- view -----------------------------------------------------------------

  resize() {
    const box = (this.canvas.parentElement ?? this.canvas).getBoundingClientRect();
    this.W = Math.max(1, box.width);
    this.H = Math.max(1, box.height);
    this.dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(this.W * this.dpr);
    this.canvas.height = Math.round(this.H * this.dpr);
    this.canvas.style.width = `${this.W}px`;
    this.canvas.style.height = `${this.H}px`;
    this.paint();
  }

  zoomBy(factor: number) {
    select(this.canvas).transition().duration(250).call(this.zoomer.scaleBy, factor);
  }

  fit(animate = true) {
    if (!this.nodes.length) return;
    const xs = this.nodes.map((n) => n.x).sort((a, b) => a - b);
    const ys = this.nodes.map((n) => n.y).sort((a, b) => a - b);
    const q = (a: number[], p: number) => a[Math.min(a.length - 1, Math.floor(p * a.length))];
    const lo = this.mode === "constellation" ? 0.02 : 0.03;
    const x0 = q(xs, lo), x1 = q(xs, 1 - lo), y0 = q(ys, lo), y1 = q(ys, 1 - lo);
    const pad = this.mode === "constellation" ? 20 : 90;
    const k = Math.max(0.12, Math.min(this.mode === "constellation" ? 9 : 3, 0.9 / Math.max((x1 - x0 + pad) / this.W, (y1 - y0 + pad) / this.H)));
    const t = zoomIdentity.translate((-(x0 + x1) / 2) * k, (-(y0 + y1) / 2) * k).scale(k);
    const sel = select(this.canvas);
    if (animate) sel.transition().duration(500).call(this.zoomer.transform, t);
    else sel.call(this.zoomer.transform, t);
  }

  toScreen(n: GNode): [number, number] {
    return [this.W / 2 + this.transform.x + n.x * this.transform.k, this.H / 2 + this.transform.y + n.y * this.transform.k];
  }

  private hit(mx: number, my: number): GNode | null {
    if (!this.quad) this.quad = quadtree<GNode>(this.nodes, (n) => n.x, (n) => n.y);
    const k = this.transform.k;
    const gx = (mx - this.W / 2 - this.transform.x) / k;
    const gy = (my - this.H / 2 - this.transform.y) / k;
    const n = this.quad.find(gx, gy, 24 / k);
    if (!n) return null;
    return Math.hypot(n.x - gx, n.y - gy) <= n.r + 4 / k ? n : null;
  }

  // --- events ---------------------------------------------------------------

  private onMove = (e: MouseEvent) => {
    const [x, y] = pointer(e, this.canvas);
    const n = this.hit(x, y);
    if (n !== this.hovered) {
      this.hovered = n;
      this.paint();
    }
    this.canvas.style.cursor = n ? "pointer" : "";
    this.events.onHover(n, x, y);
  };
  private onLeave = () => {
    this.hovered = null;
    this.paint();
    this.events.onHover(null, 0, 0);
  };
  private onClick = (e: MouseEvent) => {
    const [x, y] = pointer(e, this.canvas);
    this.events.onClick(this.hit(x, y));
  };
  private onDouble = (e: MouseEvent) => {
    const [x, y] = pointer(e, this.canvas);
    const n = this.hit(x, y);
    if (n) this.events.onDoubleClick(n);
  };

  // --- paint ----------------------------------------------------------------

  private tone(n: GNode): string {
    const tier = tierOf(n.tag?.dimension);
    return tier === "theme" ? this.palette.theme : tier === "entity" ? this.palette.entity : this.palette.meta;
  }

  paint() {
    const { ctx, W, H, dpr, palette } = this;
    const k = this.transform.k;
    const focus = this.hovered ?? this.selected;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.translate(W / 2 + this.transform.x, H / 2 + this.transform.y);
    ctx.scale(k, k);
    ctx.lineCap = "round";

    // Edges: the unrelated ones first and faint, then the ones that touch the focus.
    if (this.mode === "tags") {
      for (const l of this.links) {
        const near = focus && (l.source === focus || l.target === focus);
        if (focus && !near) continue;
        ctx.beginPath();
        ctx.moveTo(l.source.x, l.source.y);
        ctx.lineTo(l.target.x, l.target.y);
        ctx.strokeStyle = near ? palette.edgeFocus : palette.edge;
        ctx.globalAlpha = near ? 0.8 : 0.55;
        ctx.lineWidth = (0.6 + 2.4 * Math.sqrt(l.w / this.wmax)) / Math.sqrt(k);
        ctx.stroke();
      }
      if (focus) {
        ctx.globalAlpha = 0.08;
        ctx.strokeStyle = palette.edge;
        for (const l of this.links) {
          if (l.source === focus || l.target === focus) continue;
          ctx.beginPath();
          ctx.moveTo(l.source.x, l.source.y);
          ctx.lineTo(l.target.x, l.target.y);
          ctx.lineWidth = (0.6 + 2.4 * Math.sqrt(l.w / this.wmax)) / Math.sqrt(k);
          ctx.stroke();
        }
      }
    } else {
      for (const pass of ["tag", "post"] as const) {
        ctx.beginPath();
        for (const l of this.links) {
          if ((l.kind === "tag") !== (pass === "tag")) continue;
          if (focus && l.source !== focus && l.target !== focus) continue;
          ctx.moveTo(l.source.x, l.source.y);
          ctx.lineTo(l.target.x, l.target.y);
        }
        ctx.strokeStyle = pass === "tag" ? (focus ? palette.edgeFocus : palette.edge) : palette.edgePost;
        ctx.globalAlpha = pass === "tag" ? (focus ? 0.55 : 0.6) : 0.55;
        ctx.lineWidth = (pass === "tag" ? 0.7 : 1.3) / k;
        ctx.stroke();
      }
      if (focus) {
        ctx.beginPath();
        for (const l of this.links) {
          if (l.source === focus || l.target === focus) continue;
          ctx.moveTo(l.source.x, l.source.y);
          ctx.lineTo(l.target.x, l.target.y);
        }
        ctx.strokeStyle = palette.edge;
        ctx.globalAlpha = 0.14;
        ctx.lineWidth = 0.7 / k;
        ctx.stroke();
      }
    }

    // Nodes.
    for (const n of this.nodes) {
      const dim = !!focus && n !== focus && !focus.nb.has(n);
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      if (n.kind === "tag") {
        ctx.fillStyle = this.tone(n);
        ctx.globalAlpha = dim ? 0.12 : 0.95;
      } else {
        ctx.fillStyle = n.deg ? palette.post : palette.isolate;
        ctx.globalAlpha = dim ? 0.1 : n.deg ? 0.78 : 0.6;
      }
      ctx.fill();
      if (n === focus || n === this.selected) {
        ctx.globalAlpha = 1;
        ctx.lineWidth = 2 / k;
        ctx.strokeStyle = palette.post;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // Labels. Subjects keep theirs; posts earn one by zoom or by being near the focus.
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.lineJoin = "round";
    ctx.strokeStyle = palette.halo;
    for (const n of this.nodes) {
      if (focus && n !== focus && !focus.nb.has(n)) continue;
      const text = this.events.labelOf(n);
      if (!text) continue;
      if (n.kind === "tag") {
        const screen = this.mode === "tags" ? Math.max(10, Math.min(17, 8 + n.r * 0.45)) : Math.max(10, Math.min(15, 7 + n.r * 0.5));
        const always = this.mode === "tags" || n.rank < LABELLED_HUBS || n === focus || (!!focus && focus.nb.has(n));
        const shrink = always ? 1 : Math.min(1, k / 1.4);
        if (!always && screen * shrink < 8.5) continue;
        const fs = (screen * shrink) / k;
        ctx.font = `600 ${fs}px ${palette.font}`;
        ctx.fillStyle = this.tone(n);
        ctx.lineWidth = 3 / k;
        ctx.strokeText(text, n.x, n.y + n.r + 2 / k);
        ctx.fillText(text, n.x, n.y + n.r + 2 / k);
      } else if (k > 2.2 || (focus && (n === focus || (k > 1.1 && focus.nb.has(n))))) {
        const fs = 9 / k;
        ctx.font = `500 ${fs}px ${palette.font}`;
        ctx.fillStyle = palette.post;
        ctx.lineWidth = 3 / k;
        const s = text.length > 42 ? `${text.slice(0, 41)}…` : text;
        ctx.strokeText(s, n.x, n.y + n.r + 1.5 / k);
        ctx.fillText(s, n.x, n.y + n.r + 1.5 / k);
      }
    }
  }
}
