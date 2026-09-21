import { getLocale } from "next-intl/server";
import { Histogram } from "@/components/tags/Histogram";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { ChannelStats } from "@/lib/types";

export const metadata = { title: "Stats" };

export default async function StatsPage() {
  const [stats, locale] = await Promise.all([apiFetch<ChannelStats>("/api/stats"), getLocale()]);
  const firstYear = stats.first_post_at ? new Date(stats.first_post_at).getFullYear() : null;
  const lastYear = stats.last_post_at ? new Date(stats.last_post_at).getFullYear() : firstYear;
  const span = firstYear ? (firstYear === lastYear ? `${firstYear}` : `${firstYear}–${lastYear}`) : "—";

  return (
    <div>
      <header className="border-b pb-6">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">The archive in numbers</h1>
        <p className="mt-2 max-w-[60ch] text-[0.9375rem] text-muted-foreground">
          Counts come from the posts held here, and views are whatever Telegram reported the last time
          each post was checked.
        </p>
      </header>

      <dl className="flex flex-wrap gap-x-12 gap-y-5 py-6">
        {[
          ["Posts", compactNumber(stats.posts)],
          ["Views in total", compactNumber(stats.total_views)],
          ["Views per post", compactNumber(stats.mean_views)],
          ["Years", span],
        ].map(([label, value]) => (
          <div key={label}>
            <dd className="stat-value">{value}</dd>
            <dt className="stat-label">{label}</dt>
          </div>
        ))}
      </dl>

      <section className="border-t py-6">
        <h2 className="mb-3 text-[0.9375rem] font-medium">How often the channel posts</h2>
        <Histogram data={stats.by_month.map((m) => ({ month: m.month, count: m.posts }))} locale={locale} />
      </section>

      {stats.top_tags.length > 0 ? (
        <section className="border-t py-6">
          <h2 className="mb-3 text-[0.9375rem] font-medium">Most covered</h2>
          <div className="flex flex-wrap gap-1.5">
            {stats.top_tags.map((t) => (
              <TagChip key={t.slug} tag={t} locale={locale} showCount />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
