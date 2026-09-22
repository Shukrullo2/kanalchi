"use client";

import { useState } from "react";

/**
 * Weekday against hour of day: when this channel actually publishes.
 *
 * A grid, not two bar charts. The marginal totals hide the thing worth seeing —
 * that a channel posts on weekday mornings but on Sunday only in the evening —
 * and only the cross-tabulation shows it. Magnitude uses the same validated
 * sequential ramp as the calendar, so both grids read the same way.
 */
export function MatrixHeatmap({
  cells,
  rowLabels,
  colLabels,
  captionTemplate,
  valueTemplate,
  legend,
}: {
  cells: { row: number; col: number; value: number }[];
  /** Seven weekday names, Monday first. */
  rowLabels: string[];
  /** Twenty-four hour labels. */
  colLabels: string[];
  /** Written with {row}, {col} and {value}. A string, not a callback: a server
   *  page cannot hand a function to a client component. */
  captionTemplate: string;
  /** How the count itself is written, e.g. "{value} posts". */
  valueTemplate: string;
  legend: { less: string; more: string };
}) {
  const [hover, setHover] = useState<{ row: number; col: number } | null>(null);
  const lookup = new Map(cells.map((c) => [`${c.row}:${c.col}`, c.value]));
  const max = Math.max(1, ...cells.map((c) => c.value));
  const level = (n: number) => (n === 0 ? 0 : Math.min(5, 1 + Math.floor((n / max) * 4.999)));
  const active = hover ? lookup.get(`${hover.row}:${hover.col}`) ?? 0 : null;

  return (
    <figure className="m-0">
      <div className="no-scrollbar overflow-x-auto pb-1">
        <table className="matrix" role="img">
          <tbody>
            {rowLabels.map((rowLabel, r) => (
              <tr key={rowLabel}>
                <th scope="row">{rowLabel}</th>
                {colLabels.map((_, c) => {
                  const value = lookup.get(`${r + 1}:${c}`) ?? 0;
                  return (
                    <td key={c}>
                      <span
                        className="heat-cell block"
                        data-level={level(value)}
                        data-hover={hover?.row === r + 1 && hover?.col === c}
                        onMouseEnter={() => setHover({ row: r + 1, col: c })}
                        onMouseLeave={() => setHover(null)}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="matrix-axis">
              <th />
              {colLabels.map((label, c) => (
                <td key={c}>{c % 3 === 0 ? label : ""}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
        <figcaption className="chart-caption mt-0">
          {hover
            ? captionTemplate
                .replace("{row}", rowLabels[hover.row - 1])
                .replace("{col}", colLabels[hover.col])
                .replace("{value}", valueTemplate.replace("{value}", String(active ?? 0)))
            : ""}
        </figcaption>
        <span className="heat-legend">
          {legend.less}
          {[0, 1, 2, 3, 4, 5].map((l) => (
            <i key={l} style={{ background: `var(--heat-${l})` }} />
          ))}
          {legend.more}
        </span>
      </div>
    </figure>
  );
}
