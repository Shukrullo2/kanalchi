"use client";

import { useState } from "react";

/**
 * Daily model spend.
 *
 * One series, so no legend — the heading names it. The value appears on hover
 * rather than being printed over every bar, and the axis is just the two ends of
 * the range; the grid would only compete with the marks.
 */
export function SpendBars({ data }: { data: { day: string; usd: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (data.length === 0) return null;

  const max = Math.max(0.0001, ...data.map((d) => d.usd));
  const active = hover !== null ? data[hover] : null;

  return (
    <figure className="m-0">
      <div className="flex h-24 items-end gap-[2px]" role="img" aria-label="spend per day">
        {data.map((d, i) => (
          <button
            key={d.day}
            type="button"
            tabIndex={-1}
            aria-hidden
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            className="flex h-full min-w-[3px] flex-1 items-end"
          >
            <span
              className="w-full rounded-t-[2px] bg-primary transition-opacity"
              style={{
                height: `${Math.max(2, (d.usd / max) * 96)}px`,
                opacity: hover === null ? 0.8 : hover === i ? 1 : 0.28,
              }}
            />
          </button>
        ))}
      </div>
      <figcaption className="mt-1.5 flex justify-between text-[0.7rem] tabular-nums text-muted-foreground">
        {active ? (
          <span className="text-foreground">
            {active.day} — ${active.usd.toFixed(3)}
          </span>
        ) : (
          <span>{data[0].day}</span>
        )}
        <span>{data[data.length - 1].day}</span>
      </figcaption>
    </figure>
  );
}
