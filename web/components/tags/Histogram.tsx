"use client";

import { useState } from "react";
import { toneVar } from "@/lib/dimensions";
import { monthLabel } from "@/lib/format";

/**
 * Posts per month for one subject — how long the channel has been on a story and
 * when it was loudest.
 *
 * Bars are thin with a 2px gap so adjacent months stay countable, the axis is
 * only the two ends of the range, and the value appears on hover rather than
 * printing a number over every bar.
 */
export function Histogram({
  data,
  tone,
  locale = "en",
}: {
  data: { month: string; count: number }[];
  tone?: string | null;
  locale?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length < 2) return null;

  const max = Math.max(...data.map((d) => d.count));
  const colour = tone ? toneVar(tone) : "var(--primary)";
  const active = hover !== null ? data[hover] : null;

  return (
    <figure className="m-0">
      <div className="flex h-16 items-end gap-[2px]" role="img" aria-label="posts per month">
        {data.map((d, i) => (
          <button
            key={d.month}
            type="button"
            tabIndex={-1}
            aria-hidden
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            className="flex h-full min-w-[3px] flex-1 items-end"
          >
            <span
              className="w-full rounded-t-[2px] transition-opacity"
              style={{
                height: `${Math.max(3, (d.count / max) * 64)}px`,
                background: colour,
                opacity: hover === null ? 0.75 : hover === i ? 1 : 0.3,
              }}
            />
          </button>
        ))}
      </div>
      <figcaption className="mt-1.5 flex justify-between text-[0.7rem] tabular-nums text-muted-foreground">
        {active ? (
          <span className="text-foreground">
            {monthLabel(active.month, locale)} — {active.count}
          </span>
        ) : (
          <span>{monthLabel(data[0].month, locale)}</span>
        )}
        <span>{monthLabel(data[data.length - 1].month, locale)}</span>
      </figcaption>
    </figure>
  );
}
