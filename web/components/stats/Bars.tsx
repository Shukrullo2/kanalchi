"use client";

import { useState } from "react";
import { compactNumber } from "@/lib/format";

export type Bar = { label: string; value: number; hint?: string };

/**
 * A single-series column chart.
 *
 * Every column is the same hue: the categories are nominal, and colouring them by
 * value would spend colour re-saying what height already says. No legend, since
 * the section heading names the one series. Values appear on hover in a caption
 * line rather than as a number stamped on every column.
 */
export function Bars({
  data,
  height = 112,
  template = "{value}",
  compact = false,
  everyNthLabel = 1,
  caption,
}: {
  data: Bar[];
  height?: number;
  /** How a value is written, e.g. "{value} posts". A string, because a server page
   *  cannot hand a function across to a client component. */
  template?: string;
  /** Write large values as 12K / 1.2M. */
  compact?: boolean;
  /** Show only every nth axis label when there are too many to fit. */
  everyNthLabel?: number;
  /** What the caption says when nothing is hovered. */
  caption?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length === 0) return null;
  const max = Math.max(1, ...data.map((d) => d.value));
  const active = hover !== null ? data[hover] : null;
  const format = (v: number) => template.replace("{value}", compact ? compactNumber(v) : String(v));

  return (
    <figure className="m-0">
      <div className="bars" style={{ "--bars-h": `${height}px` } as React.CSSProperties} role="img">
        {data.map((d, i) => (
          <button
            key={i}
            type="button"
            tabIndex={-1}
            aria-hidden
            className="bars-slot"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <span
              className="bars-col"
              style={{
                height: `${Math.max(2, (d.value / max) * height)}px`,
                opacity: hover === null ? 0.85 : hover === i ? 1 : 0.3,
              }}
            />
          </button>
        ))}
      </div>
      <div className="bars-axis" aria-hidden>
        {data.map((d, i) => (
          <span key={i}>{i % everyNthLabel === 0 ? d.label : ""}</span>
        ))}
      </div>
      <figcaption className="chart-caption">
        {active ? (
          <>
            <strong>{active.label}</strong> — {format(active.value)}
            {active.hint ? ` · ${active.hint}` : ""}
          </>
        ) : (
          (caption ?? "")
        )}
      </figcaption>
    </figure>
  );
}
