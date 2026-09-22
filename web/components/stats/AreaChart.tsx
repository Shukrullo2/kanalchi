"use client";

import { useState } from "react";

export type Point = { label: string; value: number };

/**
 * A trend over time: one series, drawn as a line with a soft fill under it.
 *
 * Columns were the wrong form here — a hundred monthly bars read as a comb, and
 * the eye has to reconstruct the shape. A line states the shape directly. The
 * crosshair gives the value at a point rather than printing all hundred.
 */
export function AreaChart({
  data,
  height = 140,
  template = "{value}",
  cumulative = false,
}: {
  data: Point[];
  height?: number;
  template?: string;
  /** Plot the running total instead of the per-period value. */
  cumulative?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length < 2) return null;

  const series: Point[] = [];
  for (const d of data) {
    const previous = series[series.length - 1]?.value ?? 0;
    series.push({ label: d.label, value: cumulative ? previous + d.value : d.value });
  }

  const W = 1000;
  const max = Math.max(1, ...series.map((d) => d.value));
  const x = (i: number) => (i / (series.length - 1)) * W;
  const y = (v: number) => height - (v / max) * (height - 8) - 2;
  const line = series.map((d, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join(" ");
  const area = `${line} L${W},${height} L0,${height} Z`;
  const active = hover !== null ? series[hover] : null;

  return (
    <figure className="m-0">
      <div
        className="relative"
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const ratio = (e.clientX - box.left) / box.width;
          setHover(Math.max(0, Math.min(series.length - 1, Math.round(ratio * (series.length - 1)))));
        }}
      >
        <svg viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" className="block w-full" style={{ height }} role="img">
          <path d={area} fill="var(--chart-1)" opacity="0.16" />
          <path d={line} fill="none" stroke="var(--chart-1)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          {active && hover !== null ? (
            <>
              <line x1={x(hover)} y1="0" x2={x(hover)} y2={height} stroke="var(--border-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <circle cx={x(hover)} cy={y(active.value)} r="4" fill="var(--chart-1)" stroke="var(--background)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            </>
          ) : null}
        </svg>
      </div>
      <div className="bars-axis">
        <span className="text-left">{series[0].label}</span>
        <span className="text-right">{series[series.length - 1].label}</span>
      </div>
      <figcaption className="chart-caption">
        {active ? (
          <>
            <strong>{active.label}</strong> — {template.replace("{value}", String(active.value))}
          </>
        ) : (
          ""
        )}
      </figcaption>
    </figure>
  );
}
