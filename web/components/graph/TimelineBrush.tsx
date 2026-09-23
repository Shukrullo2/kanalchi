"use client";

import { brushX, type D3BrushEvent } from "d3-brush";
import { scaleLinear, scaleUtc } from "d3-scale";
import { select } from "d3-selection";
import { useEffect, useRef } from "react";
import { monthLabel } from "@/lib/format";
import { dayMs, isoDay } from "@/lib/graph";

const DAY = 86_400_000;
const HEIGHT = 58;

/**
 * The range picker under the map: the whole archive as monthly bars, with a
 * brush over the window being shown. The reader picks a period by the shape
 * of the archive rather than by typing dates, and the bars say where the
 * channel was busy before the map is even drawn.
 */
export function TimelineBrush({
  months,
  from,
  to,
  locale,
  onChange,
}: {
  months: { month: string; count: number }[];
  from: string;
  to: string;
  locale: string;
  onChange: (from: string, to: string) => void;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const change = useRef(onChange);
  useEffect(() => {
    change.current = onChange;
  });

  useEffect(() => {
    const svg = ref.current;
    if (!svg || months.length === 0) return;

    const draw = () => {
      const W = Math.max(200, svg.clientWidth);
      const m = { l: 4, r: 4, t: 4, b: 16 };
      const sel = select(svg);
      sel.attr("viewBox", `0 0 ${W} ${HEIGHT}`);
      sel.selectAll("*").remove();

      const first = dayMs(`${months[0].month}-01`);
      const last = Math.max(dayMs(to) + DAY, Date.now());
      const x = scaleUtc().domain([first, last]).range([m.l, W - m.r]);
      const y = scaleLinear()
        .domain([0, Math.max(1, ...months.map((d) => d.count))])
        .range([HEIGHT - m.b, m.t]);

      const bars = sel.append("g");
      for (const d of months) {
        const a = dayMs(`${d.month}-01`);
        const next = new Date(a);
        next.setUTCMonth(next.getUTCMonth() + 1);
        bars
          .append("rect")
          .attr("class", "graph-tl-bar")
          .attr("x", x(a) + 0.5)
          .attr("width", Math.max(1, x(+next) - x(a) - 1))
          .attr("y", y(d.count))
          .attr("height", HEIGHT - m.b - y(d.count));
      }

      // One label about every eighty pixels, always on a month boundary.
      const every = Math.max(1, Math.ceil(months.length / Math.max(1, Math.floor((W - 8) / 80))));
      const axis = sel.append("g").attr("class", "graph-tl-axis");
      months.forEach((d, i) => {
        if (i % every) return;
        axis
          .append("text")
          .attr("x", x(dayMs(`${d.month}-01`)) + 2)
          .attr("y", HEIGHT - 3)
          .text(monthLabel(d.month, locale));
      });

      const brush = brushX()
        .extent([
          [m.l, m.t],
          [W - m.r, HEIGHT - m.b],
        ])
        .on("end", (e: D3BrushEvent<unknown>) => {
          if (!e.sourceEvent || !e.selection) return;
          const [a, b] = (e.selection as [number, number]).map((px) => +x.invert(px));
          change.current(isoDay(a), isoDay(Math.max(a, b - 1)));
        });
      sel.append("g").attr("class", "graph-tl-brush").call(brush).call(brush.move, [x(dayMs(from)), x(dayMs(to) + DAY)]);
    };

    draw();
    const ro = new ResizeObserver(draw);
    ro.observe(svg);
    return () => ro.disconnect();
  }, [months, from, to, locale]);

  return <svg ref={ref} className="graph-tl" aria-hidden />;
}
