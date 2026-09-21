import { getLocale } from "next-intl/server";
import { Histogram } from "@/components/tags/Histogram";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch } from "@/lib/api";
import type { ChannelStats } from "@/lib/types";

export const metadata = { title: "Stats" };

function compact(n: number) {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export default async function StatsPage() {
  const [stats, locale] = await Promise.all([apiFetch<ChannelStats>("/api/stats"), getLocale()]);
  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Posts" value={compact(stats.posts)} />
        <Stat label="Total views" value={compact(stats.total_views)} />
        <Stat label="Average views" value={compact(stats.mean_views)} />
        <Stat
          label="Archive span"
          value={
            stats.first_post_at
              ? `${new Date(stats.first_post_at).getFullYear()}–${new Date(stats.last_post_at ?? stats.first_post_at).getFullYear()}`
              : "—"
          }
        />
      </dl>

      <section>
        <h2 className="mb-2 text-sm font-medium">Posts per month</h2>
        <Histogram data={stats.by_month.map((m) => ({ month: m.month, count: m.posts }))} />
      </section>

      <section>
        <h2 className="mb-2 text-sm font-medium">Most covered</h2>
        <div className="flex flex-wrap gap-1.5">
          {stats.top_tags.map((t) => (
            <TagChip key={t.slug} tag={t} locale={locale} showCount />
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xl font-semibold">{value}</dd>
    </div>
  );
}
