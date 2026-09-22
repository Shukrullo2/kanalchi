import Link from "next/link";

export type Ranked = { label: string; value: number; href?: string; hint?: string };

/**
 * A ranked list with the bar behind the name.
 *
 * For a handful of long, named categories — domains, people, ministries — a
 * horizontal row reads far better than a column chart, because the label sits
 * on its own baseline instead of being turned on its side or truncated.
 */
export function RankedBars({
  rows,
  format = (v) => String(v),
  ordinal = false,
}: {
  rows: Ranked[];
  format?: (value: number) => string;
  /** Use the sequential ramp, for buckets whose order is part of the meaning. */
  ordinal?: boolean;
}) {
  if (rows.length === 0) return null;
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <ul className="ranked">
      {rows.map((row, i) => {
        const inner = (
          <>
            <span
              className="ranked-fill"
              style={{
                width: `${Math.max(1.5, (row.value / max) * 100)}%`,
                background: ordinal ? `var(--heat-${Math.min(5, 1 + Math.floor((row.value / max) * 4.999))})` : "var(--chart-1)",
              }}
              aria-hidden
            />
            <span className="ranked-label">{row.label}</span>
            {row.hint ? <span className="ranked-hint">{row.hint}</span> : null}
            <span className="ranked-value">{format(row.value)}</span>
          </>
        );
        return (
          <li key={`${row.label}-${i}`}>
            {row.href ? (
              <Link href={row.href} className="ranked-row">
                {inner}
              </Link>
            ) : (
              <div className="ranked-row">{inner}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

/**
 * One bar, split into shares — for a mix that genuinely adds up to the whole.
 * Segments are steps of a single ramp, in size order, with a keyed legend, so
 * nothing depends on telling six hues apart.
 */
export function ProportionBar({
  parts,
  format = (v) => String(v),
}: {
  parts: { label: string; value: number }[];
  format?: (value: number) => string;
}) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  if (total === 0) return null;
  const shown = parts.slice(0, 5);

  return (
    <div>
      <div className="proportion">
        {shown.map((p, i) => (
          <span
            key={p.label}
            className="proportion-part"
            style={{ width: `${(p.value / total) * 100}%`, background: `var(--heat-${5 - i})` }}
            title={p.label}
          />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-sm">
        {shown.map((p, i) => (
          <li key={p.label} className="flex items-center gap-2">
            <i className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: `var(--heat-${5 - i})` }} aria-hidden />
            <span>{p.label}</span>
            <span className="tnum text-muted-foreground">
              {format(p.value)} · {Math.round((p.value / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
