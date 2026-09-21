import { getLocale } from "next-intl/server";
import { ChartIcon } from "@/components/Icons";
import { Histogram } from "@/components/tags/Histogram";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { ChannelStats } from "@/lib/types";

export const metadata = { title: "Stats" };

export default async function StatsPage() {
  const [stats, locale] = await Promise.all([apiFetch<ChannelStats>("/api/stats"), getLocale()]);
  const span = stats.first_post_at
    ? `${new Date(stats.first_post_at).getFullYear()}–${new Date(stats.last_post_at ?? stats.first_post_at).getFullYear()}`
    : "—";

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-2">
        <ChartIcon size={18} className="text-primary" />
        <h1 className="text-xl font-semibold tracking-tight">Stats</h1>
      </header>

      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          ["Posts", compactNumber(stats.posts)],
          ["Total views", compactNumber(stats.total_views)],
          ["Average views", compactNumber(stats.mean_views)],
          ["Archive", span],
        ].map(([label, value]) => (
          <div key={label} className="stat-tile">
            <dt className="stat-label">{label}</dt>
            <dd className="stat-value">{value}</dd>
          </div>
        ))}
      </dl>

      <section className="card-surface p-4 sm:p-5">
        <h2 className="mb-3 text-sm font-medium">Posts per month</h2>
        <Histogram data={stats.by_month.map((m) => ({ month: m.month, count: m.posts }))} locale={locale} />
      </section>

      <section className="card-surface p-4 sm:p-5">
        <h2 className="mb-3 text-sm font-medium">Most covered</h2>
        <div className="flex flex-wrap gap-1.5">
          {stats.top_tags.map((t) => (
            <TagChip key={t.slug} tag={t} locale={locale} showCount />
          ))}
        </div>
      </section>
    </div>
  );
}
