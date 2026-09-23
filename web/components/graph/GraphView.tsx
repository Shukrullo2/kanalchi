"use client";

import { usePathname, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { SearchIcon } from "@/components/Icons";
import { tierOf, toneVar } from "@/lib/dimensions";
import { compactNumber, postDate } from "@/lib/format";
import {
  buildConstellation,
  buildTagMap,
  dimensionsIn,
  filterPosts,
  tagUse,
  type GNode,
  type Mode,
} from "@/lib/graph";
import { tagLabel } from "@/lib/labels";
import type { GraphOut, GraphTag } from "@/lib/types";
import { GraphEngine, type EngineEvents } from "./engine";
import { NodePanel } from "./NodePanel";
import { PanelToggle } from "./PanelToggle";
import { TimelineBrush } from "./TimelineBrush";
import { isNarrow, usePanel } from "./usePanel";
import "./graph.css";

const DAY = 86_400_000;
const QUICK: { key: "days30" | "days90" | "months6" | "year1"; days: number }[] = [
  { key: "days30", days: 30 },
  { key: "days90", days: 90 },
  { key: "months6", days: 182 },
  { key: "year1", days: 365 },
];
const TIER_RANK = { theme: 0, entity: 1, meta: 2 } as const;
export type GraphInitial = { mode: Mode; tags: string[]; off: string[]; q: string };

/**
 * The map page's client half: the canvas is the page, the controls float over
 * it in a panel that can be put away, and whatever was clicked gets a panel of
 * its own on the other side.
 *
 * The subjects-only map is the default: it is readable at any window size,
 * and the constellation of every post is a mode for when the dots matter.
 * Only the date window goes to the server, since that is what decides which
 * posts exist. Everything else — search, the subjects picked out, which
 * dimensions are shown, which of the two maps is drawn — is a filter over the
 * posts already here, and is applied on every keystroke without a request.
 * All of it still lands in the URL, so a view can be shared.
 */
export function GraphView({
  data,
  locale,
  dimensionLabels,
  initial,
}: {
  data: GraphOut;
  locale: string;
  dimensionLabels: Record<string, string>;
  initial: GraphInitial;
}) {
  const t = useTranslations("graph");
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();

  const [mode, setMode] = useState<Mode>(initial.mode);
  const [q, setQ] = useState(initial.q);
  const [picked, setPicked] = useState<Set<string>>(() => new Set(initial.tags));
  const [off, setOff] = useState<Set<string>>(() => new Set(initial.off));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { open, toggle: togglePanel, dismiss: dismissPanel } = usePanel("kanalchi.graph.panel");
  const [tip, setTip] = useState<{ x: number; y: number; node: GNode } | null>(null);

  const labelOf = useCallback((tag: GraphTag) => tagLabel(tag, locale), [locale]);
  const dimLabel = useCallback(
    (key: string | null) => (key ? (dimensionLabels[key] ?? key.replace(/^custom_/, "").replace(/_/g, " ")) : ""),
    [dimensionLabels],
  );

  // --- derived --------------------------------------------------------------
  const dimensions = useMemo(() => dimensionsIn(data, (d) => TIER_RANK[tierOf(d)]), [data]);
  const dims = useMemo(() => new Set(dimensions.map((d) => d.key).filter((k) => !off.has(k))), [dimensions, off]);
  const tagText = useMemo(() => data.tags.map((tag) => labelOf(tag).toLowerCase()), [data, labelOf]);
  const posts = useMemo(() => filterPosts(data, { q, tags: picked, dims }, tagText), [data, q, picked, dims, tagText]);
  const use = useMemo(() => tagUse(posts, data, dims), [posts, data, dims]);
  const graph = useMemo(
    () => (mode === "tags" ? buildTagMap(posts, data, use) : buildConstellation(posts, data, use)),
    [mode, posts, data, use],
  );
  const selected = useMemo(() => graph.nodes.find((n) => n.id === selectedId) ?? null, [graph, selectedId]);

  // --- engine ---------------------------------------------------------------
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<GraphEngine | null>(null);
  // The engine lives across renders; it calls through this ref so it always sees the latest closures.
  const events = useRef<EngineEvents>({ labelOf: () => "", onHover: () => {}, onClick: () => {}, onDoubleClick: () => {} });
  useEffect(() => {
    events.current = {
      labelOf: (n) => (n.kind === "tag" ? labelOf(n.tag!) : n.post!.title),
      onHover: (n, x, y) => setTip(n ? { x, y, node: n } : null),
      onClick: (n) => {
        setSelectedId(n ? n.id : null);
        // On a phone the details sheet and the controls sheet share the bottom edge.
        if (n && isNarrow()) dismissPanel();
      },
      onDoubleClick: (n) => {
        if (n.kind === "tag") toggleTag(n.tag!.slug);
      },
    };
  });
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const engine = new GraphEngine(canvas, {
      labelOf: (n) => events.current.labelOf(n),
      onHover: (n, x, y) => events.current.onHover(n, x, y),
      onClick: (n) => events.current.onClick(n),
      onDoubleClick: (n) => events.current.onDoubleClick(n),
    });
    engineRef.current = engine;
    return () => {
      engine.destroy();
      engineRef.current = null;
    };
  }, []);
  // The canvas fills the window under floating UI: the header and zoom buttons along the top,
  // the controls panel on the left (a bottom sheet on a phone) and the legend along the bottom.
  // The engine fits the graph into what is left, so the first view is not half hidden.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const measure = () => {
      const box = canvas.getBoundingClientRect();
      const gap = 8;
      // Hidden elements (the legend on a phone, a closed panel) measure 0×0 at the origin.
      const visible = (el: Element | null | undefined) => {
        const r = el?.getBoundingClientRect();
        return r && r.width > 0 && r.height > 0 ? r : null;
      };
      const root = canvas.closest(".graph");
      const hud = visible(root?.querySelector(".graph-hud"));
      const legend = visible(root?.querySelector(".graph-legend"));
      const panel = document.getElementById("graph-controls");
      const shown = panel?.dataset.open === "true" ? visible(panel) : null;
      const sheet = shown && isNarrow();
      engineRef.current?.setInsets({
        top: hud ? Math.max(0, hud.bottom - box.top + gap) : 0,
        right: 0,
        bottom: Math.max(
          legend ? box.bottom - legend.top + gap : 0,
          sheet ? box.bottom - shown.top + gap : 0,
        ),
        left: shown && !sheet ? Math.max(0, shown.right - box.left + gap) : 0,
      });
    };
    measure();
    const watch = new ResizeObserver(measure);
    const panel = document.getElementById("graph-controls");
    if (panel) watch.observe(panel);
    watch.observe(canvas);
    return () => watch.disconnect();
  }, [open]);
  useEffect(() => {
    engineRef.current?.setGraph(graph, mode);
  }, [graph, mode]);
  useEffect(() => {
    engineRef.current?.setSelected(selectedId);
  }, [selectedId, graph]);

  // --- url ------------------------------------------------------------------
  useEffect(() => {
    const url = new URL(window.location.href);
    const set = (key: string, value: string) => (value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    set("q", q.trim());
    set("tags", [...picked].join(","));
    set("off", [...off].join(","));
    set("mode", mode === "constellation" ? "posts" : "");
    window.history.replaceState(window.history.state, "", url);
  }, [q, picked, off, mode]);

  // The window is the server's business: it decides which posts exist. A quick
  // range is sent as a number of days and dated there, so no clock runs here.
  const changeWindow = (from: string, to: string) => {
    const params = new URLSearchParams(window.location.search);
    params.set("from", from);
    params.set("to", to);
    params.delete("days");
    startTransition(() => router.replace(`${pathname}?${params}`, { scroll: false }));
  };
  const quick = (days: number) => {
    const params = new URLSearchParams(window.location.search);
    params.delete("from");
    params.delete("to");
    params.set("days", String(days));
    startTransition(() => router.replace(`${pathname}?${params}`, { scroll: false }));
  };
  const activeQuick = QUICK.find((k) => Math.round((Date.parse(data.to) - Date.parse(data.from)) / DAY) === k.days)?.key;

  function toggleTag(slug: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }
  const toggleDim = (key: string) =>
    setOff((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const tagBySlug = (slug: string) => data.tags.find((x) => x.slug === slug);

  return (
    <div className="graph" data-pending={pending}>
      <div className="graph-stage">
        <canvas ref={canvasRef} />
        {/* An empty canvas needs a reason whether the period holds nothing or
            the filters left nothing, and from the reader's side those look
            identical. */}
        {posts.length === 0 ? <p className="graph-empty">{t("empty")}</p> : null}
        {tip ? (
          <div className="graph-tip" style={{ left: tip.x + 14, top: tip.y + 14 }} role="tooltip">
            {tip.node.kind === "tag" ? (
              <>
                <b>{labelOf(tip.node.tag!)}</b>
                <small>
                  {dimLabel(tip.node.tag!.dimension)} · {t("posts", { count: String(tip.node.tag!.count) })}
                  {mode === "tags" ? ` · ${t("neighbours", { count: String(tip.node.nb.size) })}` : ""}
                </small>
              </>
            ) : (
              <>
                <b>{tip.node.post!.title}</b>
                <small suppressHydrationWarning>
                  {postDate(tip.node.post!.date, locale)} · {t("views", { count: compactNumber(tip.node.post!.views) })}
                </small>
              </>
            )}
          </div>
        ) : null}
      </div>

      <PanelToggle open={open} onToggle={togglePanel} controls="graph-controls" showLabel={t("showControls")} hideLabel={t("hideControls")} />

      <aside id="graph-controls" className="graph-controls" data-open={open} aria-label={t("title")}>
        <header className="graph-controls-head">
          <span className="graph-controls-title">{t("title")}</span>
          <span className="graph-count tnum">
            {t("posts", { count: String(posts.length) })} · {t("tags", { count: String(use.size) })}
          </span>
        </header>

        <details open>
          <summary>{t("panelFilter")}</summary>
          <label className="search-field graph-search">
            <SearchIcon size={16} className="shrink-0 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} aria-label={t("search")} />
          </label>
          <div className="graph-chips">
            {picked.size === 0 ? (
              <span className="graph-hint">{t("hint")}</span>
            ) : (
              <>
                {[...picked].map((slug) => {
                  const tag = tagBySlug(slug);
                  return (
                    <span key={slug} className="graph-chip" style={{ "--tone": toneVar(tag?.dimension) } as React.CSSProperties}>
                      {tag ? labelOf(tag) : slug}
                      <button type="button" onClick={() => toggleTag(slug)} aria-label={t("unfilter")}>
                        ×
                      </button>
                    </span>
                  );
                })}
                <button type="button" className="graph-dim" onClick={() => setPicked(new Set())}>
                  {t("clear")}
                </button>
              </>
            )}
          </div>
        </details>

        <details open>
          <summary>{t("panelView")}</summary>
          <div className="graph-modes" role="tablist">
            <button type="button" role="tab" className="pill" data-active={mode === "tags"} aria-selected={mode === "tags"} onClick={() => setMode("tags")}>
              {t("modeTags")}
            </button>
            <button type="button" role="tab" className="pill" data-active={mode === "constellation"} aria-selected={mode === "constellation"} onClick={() => setMode("constellation")}>
              {t("modeConstellation")}
            </button>
          </div>
        </details>

        <details open>
          <summary>{t("panelGroups")}</summary>
          <div className="graph-dims">
            {dimensions.map((d) => (
              <button
                key={d.key}
                type="button"
                className="graph-dim"
                data-on={!off.has(d.key)}
                style={{ "--tone": toneVar(d.key) } as React.CSSProperties}
                onClick={() => toggleDim(d.key)}
                aria-pressed={!off.has(d.key)}
              >
                <i aria-hidden />
                {dimLabel(d.key)} <b>{d.tags}</b>
              </button>
            ))}
          </div>
        </details>

        <details open>
          <summary>{t("range")}</summary>
          <div className="graph-timeline-row">
            <span className="graph-range tnum" suppressHydrationWarning>
              {postDate(data.from, locale)} – {postDate(data.to, locale)}
            </span>
          </div>
          <div className="graph-quick">
            {QUICK.map((k) => (
              <button key={k.key} type="button" data-active={activeQuick === k.key} onClick={() => quick(k.days)}>
                {t(k.key)}
              </button>
            ))}
          </div>
          <TimelineBrush months={data.months} from={data.from} to={data.to} locale={locale} onChange={changeWindow} />
          {data.truncated ? <p className="graph-notice">{t("truncated", { count: String(data.posts.length) })}</p> : null}
        </details>
      </aside>

      <div className="graph-hud">
        <button type="button" onClick={() => engineRef.current?.zoomBy(1.5)} aria-label={t("zoomIn")} title={t("zoomIn")}>
          +
        </button>
        <button type="button" onClick={() => engineRef.current?.zoomBy(1 / 1.5)} aria-label={t("zoomOut")} title={t("zoomOut")}>
          −
        </button>
        <button type="button" onClick={() => engineRef.current?.fit(true)} aria-label={t("fit")} title={t("fit")}>
          ⌂
        </button>
      </div>

      <div className="graph-legend" aria-hidden>
        <span style={{ "--c": "var(--primary)" } as React.CSSProperties}>{t("legendTheme")}</span>
        <span style={{ "--c": "var(--accent)" } as React.CSSProperties}>{t("legendEntity")}</span>
        {mode === "tags" ? (
          <span style={{ "--c": "var(--border-strong)" } as React.CSSProperties}>{t("legendCo")}</span>
        ) : (
          <>
            <span style={{ "--c": "var(--foreground)" } as React.CSSProperties}>{t("legendPost")}</span>
            <span style={{ "--c": "var(--primary)" } as React.CSSProperties}>{t("legendLink")}</span>
          </>
        )}
      </div>

      {selected ? (
        <NodePanel
          node={selected}
          posts={posts}
          tags={data.tags}
          locale={locale}
          labelOf={labelOf}
          dimensionLabel={dimLabel}
          inFilter={selected.kind === "tag" && picked.has(selected.tag!.slug)}
          t={(key, values) => t(key, values)}
          onToggleTag={toggleTag}
          onClose={() => setSelectedId(null)}
        />
      ) : null}
    </div>
  );
}
