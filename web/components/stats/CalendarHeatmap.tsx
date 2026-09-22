"use client";

import { useState } from "react";

/**
 * One square per day, one year at a time, weeks as columns starting on Monday.
 *
 * Magnitude is a sequential ramp of one hue — five steps, validated on each
 * surface so the faintest non-zero day still reads. A day with no posts is the
 * surface itself, not step one, so "quiet" and "a little" never get confused.
 */
export function CalendarHeatmap({
  days,
  years,
  initialYear,
  labels,
}: {
  days: { day: string; posts: number }[];
  years: number[];
  initialYear: number;
  labels: { months: string[]; weekdays: string[]; less: string; more: string; postsTemplate: string };
}) {
  const [year, setYear] = useState(initialYear);
  const posts = (n: number) => labels.postsTemplate.replace("{count}", String(n));
  const [hover, setHover] = useState<string | null>(null);

  const counts = new Map(days.map((d) => [d.day, d.posts]));
  const inYear = days.filter((d) => d.day.startsWith(`${year}-`));
  const max = Math.max(1, ...inYear.map((d) => d.posts));

  // Grid: from the Monday on or before Jan 1 to the Sunday on or after Dec 31.
  const first = new Date(Date.UTC(year, 0, 1));
  const start = new Date(first);
  start.setUTCDate(first.getUTCDate() - ((first.getUTCDay() + 6) % 7));
  const last = new Date(Date.UTC(year, 11, 31));
  const end = new Date(last);
  end.setUTCDate(last.getUTCDate() + ((7 - last.getUTCDay()) % 7));

  const cells: { key: string; inYear: boolean; posts: number; month: number; col: number }[] = [];
  const monthStarts: { col: number; month: number }[] = [];
  for (let d = new Date(start), col = 0; d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const key = d.toISOString().slice(0, 10);
    const isMonday = d.getUTCDay() === 1;
    if (isMonday && cells.length) col += 1;
    const inside = d.getUTCFullYear() === year;
    if (inside && d.getUTCDate() <= 7 && isMonday) monthStarts.push({ col, month: d.getUTCMonth() });
    cells.push({ key, inYear: inside, posts: counts.get(key) ?? 0, month: d.getUTCMonth(), col });
  }
  const columns = (cells[cells.length - 1]?.col ?? 0) + 1;

  const level = (n: number) => (n === 0 ? 0 : Math.min(5, 1 + Math.floor((n / max) * 4.999)));
  const active = hover ? { day: hover, posts: counts.get(hover) ?? 0 } : null;
  const total = inYear.reduce((s, d) => s + d.posts, 0);

  return (
    <figure className="m-0">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {years.map((y) => (
          <button key={y} type="button" className="pill py-1 text-xs" data-active={y === year} onClick={() => setYear(y)}>
            {y}
          </button>
        ))}
      </div>

      <div className="no-scrollbar overflow-x-auto pb-1">
        <div className="inline-grid" style={{ gridTemplateColumns: `2rem repeat(${columns}, 11px)`, columnGap: 2 }}>
          <span />
          {Array.from({ length: columns }, (_, c) => {
            const m = monthStarts.find((s) => s.col === c);
            return (
              <span key={c} className="h-4 text-[0.68rem] text-muted-foreground" style={{ gridColumn: `span 1` }}>
                {m ? labels.months[m.month] : ""}
              </span>
            );
          })}

          <div className="grid" style={{ gridTemplateRows: "repeat(7, 11px)", rowGap: 2 }} aria-hidden>
            {labels.weekdays.map((w, i) => (
              <span key={w} className="text-[0.62rem] leading-[11px] text-muted-foreground">
                {i % 2 === 0 ? w : ""}
              </span>
            ))}
          </div>
          <div className="heat" style={{ gridColumn: `span ${columns}` }} role="img">
            {cells.map((c) => (
              <button
                key={c.key}
                type="button"
                tabIndex={-1}
                aria-hidden
                className="heat-cell"
                data-level={c.inYear ? level(c.posts) : 0}
                data-hover={hover === c.key}
                style={c.inYear ? undefined : { opacity: 0.25 }}
                onMouseEnter={() => c.inYear && setHover(c.key)}
                onMouseLeave={() => setHover(null)}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
        <figcaption className="chart-caption mt-0">
          {active ? (
            <>
              <strong>{active.day}</strong> — {posts(active.posts)}
            </>
          ) : (
            <>
              {year}: {posts(total)}
            </>
          )}
        </figcaption>
        <span className="heat-legend">
          {labels.less}
          {[0, 1, 2, 3, 4, 5].map((l) => (
            <i key={l} style={{ background: `var(--heat-${l})` }} />
          ))}
          {labels.more}
        </span>
      </div>
    </figure>
  );
}
