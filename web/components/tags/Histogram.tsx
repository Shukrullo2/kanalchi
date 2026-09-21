/** Monthly post counts. Bars are proportional to the busiest month. */
export function Histogram({ data }: { data: { month: string; count: number }[] }) {
  if (data.length < 2) return null;
  const max = Math.max(...data.map((d) => d.count));
  return (
    <div className="flex h-16 items-end gap-0.5" aria-label="posts per month">
      {data.map((d) => (
        <div key={d.month} className="group relative flex-1" title={`${d.month}: ${d.count}`}>
          <div
            className="w-full rounded-t bg-foreground/70 transition-colors group-hover:bg-foreground"
            style={{ height: `${Math.max(6, (d.count / max) * 64)}px` }}
          />
        </div>
      ))}
    </div>
  );
}
