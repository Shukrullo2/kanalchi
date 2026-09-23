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
  /** Strips of the canvas covered by floating UI (header, controls panel); fitting avoids them. */
  private insets = { top: 0, right: 0, bottom: 0, left: 0 };
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
        // Repulsion only reaches so far: unbounded, it flung loosely connected tags a thousand
        // units out and the fit had to zoom out until the core was an unreadable knot.
        .force("charge", forceManyBody<GNode>().strength(-260).distanceMax(320))
        .force("center", forceCenter(0, 0).strength(0.05))
        // Pull harder along the screen's short side so the map takes the screen's shape: tall on a
        // phone held upright, wide on a desktop.
        .force("x", forceX<GNode>(0).strength((n) => (n.deg ? 0.03 : 0.12) * this.aspectPull()[0]))
        .force("y", forceY<GNode>(0).strength((n) => (n.deg ? 0.035 : 0.12) * this.aspectPull()[1]))
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
    // A fresh layout (nothing carried over from the previous graph) is turned so its long axis
    // runs along the screen's long axis: an upright phone gets a tall map, a desktop a wide one.
    if (!this.nodes.some((n) => this.prev.has(n.id))) this.alignToScreen();
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
    const [oldW, oldH] = [this.W, this.H];
    this.W = Math.max(1, box.width);
    this.H = Math.max(1, box.height);
    this.dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(this.W * this.dpr);
    this.canvas.height = Math.round(this.H * this.dpr);
    this.canvas.style.width = `${this.W}px`;
    this.canvas.style.height = `${this.H}px`;
    if (this.autoFit) this.fit(false);
    else if (oldW && oldH) this.shiftBy((this.W - oldW) / 2, (this.H - oldH) / 2);
    else this.paint();
  }

  /** Tell the engine which edges are covered by floating UI, so a fit centres on what is visible. */
  setInsets(insets: { top: number; right: number; bottom: number; left: number }) {
    const prev = this.insets;
    if (["top", "right", "bottom", "left"].every((k) => Math.abs(prev[k as keyof typeof prev] - insets[k as keyof typeof insets]) < 1)) return;
    this.insets = insets;
    if (this.autoFit) this.fit(true);
    // Keep whatever the reader was looking at in the middle of the space that is left.
    else this.shiftBy((insets.left - prev.left - insets.right + prev.right) / 2, (insets.top - prev.top - insets.bottom + prev.bottom) / 2);
  }

  /** Rotate node positions about their centroid so the principal axis matches the view's long side. */
  private alignToScreen() {
    const ns = this.nodes;
    if (ns.length < 3) return;
    let mx = 0, my = 0;
    for (const n of ns) { mx += n.x; my += n.y; }
    mx /= ns.length; my /= ns.length;
    let sxx = 0, syy = 0, sxy = 0;
    for (const n of ns) {
      const dx = n.x - mx, dy = n.y - my;
      sxx += dx * dx; syy += dy * dy; sxy += dx * dy;
    }
    const major = 0.5 * Math.atan2(2 * sxy, sxx - syy); // angle of the layout's long axis
    const vw = this.W - this.insets.left - this.insets.right;
    const vh = this.H - this.insets.top - this.insets.bottom;
    const target = vh > vw * 1.15 ? Math.PI / 2 : 0;
    const a = target - major;
    const cos = Math.cos(a), sin = Math.sin(a);
    for (const n of ns) {
      const dx = n.x - mx, dy = n.y - my;
      n.x = mx + dx * cos - dy * sin;
      n.y = my + dx * sin + dy * cos;
    }
  }

  /** [x, y] multipliers for the centring forces from the visible area's shape. */
  private aspectPull(): [number, number] {
    const vw = Math.max(1, this.W - this.insets.left - this.insets.right);
    const vh = Math.max(1, this.H - this.insets.top - this.insets.bottom);
    const a = Math.max(0.6, Math.min(1.8, Math.sqrt(vh / vw)));
    return [a, 1 / a];
  }

  private shiftBy(dx: number, dy: number) {
    if (!dx && !dy) return this.paint();
    const t = zoomIdentity.translate(this.transform.x + dx, this.transform.y + dy).scale(this.transform.k);
    select(this.canvas).call(this.zoomer.transform, t);
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
    // Room in screen pixels for the labels that hang off the outermost nodes.
    const padX = this.mode === "constellation" ? 40 : 150;
    const padY = this.mode === "constellation" ? 40 : 60;
    const { top, right, bottom, left } = this.insets;
    // Fit into the part of the canvas no panel covers; a panel wider than that leaves the whole canvas.
    const vw = this.W - left - right > 120 ? this.W - left - right : this.W;
    const vh = this.H - top - bottom > 120 ? this.H - top - bottom : this.H;
    const cx = vw === this.W ? this.W / 2 : left + vw / 2;
    const cy = vh === this.H ? this.H / 2 : top + vh / 2;
    const k = Math.max(
      0.12,
      Math.min(
        this.mode === "constellation" ? 9 : 3,
        Math.max(40, vw - padX) / Math.max(1, x1 - x0),
        Math.max(40, vh - padY) / Math.max(1, y1 - y0),
      ),
    );
    // Standard d3-zoom mapping, screen = translate + k * graph: the zoom behaviour anchors wheel
    // and pinch on the pointer with exactly this formula, so nothing else may offset the view.
    const t = zoomIdentity.translate(cx - ((x0 + x1) / 2) * k, cy - ((y0 + y1) / 2) * k).scale(k);
    const sel = select(this.canvas);
    if (animate) sel.transition().duration(500).call(this.zoomer.transform, t);
    else sel.call(this.zoomer.transform, t);
  }

  toScreen(n: GNode): [number, number] {
    return [this.transform.x + n.x * this.transform.k, this.transform.y + n.y * this.transform.k];
  }

  private hit(mx: number, my: number): GNode | null {
    if (!this.quad) this.quad = quadtree<GNode>(this.nodes, (n) => n.x, (n) => n.y);
    const k = this.transform.k;
    const gx = (mx - this.transform.x) / k;
    const gy = (my - this.transform.y) / k;
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
    ctx.translate(this.transform.x, this.transform.y);
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

    // Labels. Subjects keep theirs; posts earn one by zoom or by being near the focus. They are
    // placed most important first and a label that would overlap one already placed is skipped,
    // so the first view reads as names rather than a knot, and zooming in reveals the rest.
    // The focus and its neighbours are always labelled.
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.lineJoin = "round";
    ctx.strokeStyle = palette.halo;
    const tx = this.transform.x;
    const ty = this.transform.y;
    const placed = new LabelGrid();
    const order = this.nodes
      .filter((n) => !focus || n === focus || focus.nb.has(n))
      .sort((a, b) => labelRank(b, focus) - labelRank(a, focus));
    for (const n of order) {
      const text = this.events.labelOf(n);
      if (!text) continue;
      const pinned = n === focus || (!!focus && focus.nb.has(n));
      let fs: number;
      let label = text;
      if (n.kind === "tag") {
        const screen = this.mode === "tags" ? Math.max(10, Math.min(17, 8 + n.r * 0.45)) : Math.max(10, Math.min(15, 7 + n.r * 0.5));
        const always = this.mode === "tags" || n.rank < LABELLED_HUBS || pinned;
        const shrink = always ? 1 : Math.min(1, k / 1.4);
        if (!always && screen * shrink < 8.5) continue;
        fs = (screen * shrink) / k;
        ctx.font = `600 ${fs}px ${palette.font}`;
        ctx.fillStyle = this.tone(n);
      } else if (k > 2.2 || (focus && (n === focus || (k > 1.1 && focus.nb.has(n))))) {
        fs = 9 / k;
        ctx.font = `500 ${fs}px ${palette.font}`;
        ctx.fillStyle = palette.post;
        label = text.length > 42 ? `${text.slice(0, 41)}…` : text;
      } else continue;
      const gap = (n.kind === "tag" ? 2 : 1.5) / k;
      const w = ctx.measureText(label).width * k;
      const sx = tx + n.x * k;
      const sy = ty + (n.y + n.r + gap) * k;
      const box: Box = [sx - w / 2 - 2, sy - 1, sx + w / 2 + 2, sy + fs * k + 1];
      if (!pinned && placed.hits(box)) continue;
      placed.add(box);
      ctx.lineWidth = 3 / k;
      ctx.strokeText(label, n.x, n.y + n.r + gap);
      ctx.fillText(label, n.x, n.y + n.r + gap);
    }
  }
}

type Box = [number, number, number, number];

/** Which labels win a collision: the focus, then its neighbours, then subjects by size, then posts. */
function labelRank(n: GNode, focus: GNode | null): number {
  if (n === focus) return 1e9;
  if (focus && focus.nb.has(n)) return 1e8 + n.r;
  return (n.kind === "tag" ? 1e6 : 0) + n.r;
}

/** Screen-space boxes of placed labels, bucketed so each overlap test looks at a few neighbours. */
class LabelGrid {
  private cells = new Map<string, Box[]>();
  private static SIZE = 96;
  private keys([x0, y0, x1, y1]: Box): string[] {
    const s = LabelGrid.SIZE;
    const out: string[] = [];
    for (let gx = Math.floor(x0 / s); gx <= Math.floor(x1 / s); gx++)
      for (let gy = Math.floor(y0 / s); gy <= Math.floor(y1 / s); gy++) out.push(`${gx},${gy}`);
    return out;
  }
  hits(b: Box): boolean {
    for (const key of this.keys(b))
      for (const o of this.cells.get(key) ?? []) if (b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]) return true;
    return false;
  }
  add(b: Box) {
    for (const key of this.keys(b)) {
      const list = this.cells.get(key);
      if (list) list.push(b);
      else this.cells.set(key, [b]);
    }
  }
}
