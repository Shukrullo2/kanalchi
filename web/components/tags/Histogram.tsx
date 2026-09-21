/** Monthly post counts. Bars are proportional to the busiest month in the series. */
import { monthLabel } from "@/lib/format";
export function Histogram({
  data,
  tone,
  locale = "en",
}: {
  data: { month: string; count: number }[];
  tone?: string;
  locale?: string;
}) {
  if (data.length < 2) return null;
  const max = Math.max(...data.map((d) => d.count));
  const colour = tone ? `var(--dim-${tone}, var(--primary))` : "var(--primary)";
  return (
    <div>
      <div className="flex h-14 items-end gap-[2px]" aria-label="posts per month">
        {data.map((d) => (
          <div key={d.month} className="group relative min-w-[3px] flex-1" title={`${d.month}: ${d.count}`}>
            <div
              className="w-full rounded-sm opacity-70 transition-opacity group-hover:opacity-100"
              style={{ height: `${Math.max(4, (d.count / max) * 56)}px`, background: colour }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[0.65rem] tabular-nums text-muted-foreground">
        <span>{monthLabel(data[0].month, locale)}</span>
        <span>{monthLabel(data[data.length - 1].month, locale)}</span>
      </div>
    </div>
  );
}
