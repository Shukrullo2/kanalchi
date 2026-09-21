import Link from "next/link";
import { SparkIcon } from "@/components/Icons";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { StudioOverview } from "@/lib/types";

export default async function StudioDashboard() {
  const data = await apiFetch<StudioOverview>("/api/studio/overview");
  const budgetUsed = data.studio_budget_usd ? (data.studio_spent_usd / data.studio_budget_usd) * 100 : 0;

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          ["Posts", compactNumber(data.posts)],
          ["Subscribers", data.subscribers ? compactNumber(data.subscribers) : "—"],
          ["Drafts", String(data.drafts.draft ?? 0)],
          ["Scheduled", String(data.drafts.scheduled ?? 0)],
        ].map(([label, value]) => (
          <div key={label} className="stat-tile">
            <dt className="stat-label">{label}</dt>
            <dd className="stat-value">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-3 sm:grid-cols-2">
        <Link href="/studio/drafts" className="card-surface card-hover flex items-center gap-3 p-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
            ✎
          </span>
          <span>
            <span className="block font-medium">Write a post</span>
            <span className="block text-xs text-muted-foreground">
              {data.bot_username ? `publishes via @${data.bot_username}` : "connect a bot first"}
            </span>
          </span>
        </Link>
        <Link href="/studio/research" className="card-surface card-hover flex items-center gap-3 p-4">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
            <SparkIcon size={16} />
          </span>
          <span>
            <span className="block font-medium">Research your archive</span>
            <span className="block text-xs text-muted-foreground">what you covered, and what you have not</span>
          </span>
        </Link>
      </div>

      {data.pending_tags > 0 ? (
        <Link href="/studio/tags" className="card-surface card-hover block p-4">
          <span className="font-medium">{data.pending_tags} tags waiting for review</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            Names that keep appearing in your posts but are not in the taxonomy yet.
          </span>
        </Link>
      ) : null}

      {!data.has_voice_profile ? (
        <Link href="/studio/settings" className="card-surface card-hover block p-4">
          <span className="font-medium">Teach the assistant your voice</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            It reads your own posts once, then drafts sound like you.
          </span>
        </Link>
      ) : null}

      <section className="card-surface p-4">
        <div className="mb-2 flex items-baseline justify-between text-sm">
          <span className="font-medium">Assistant spend today</span>
          <span className="tabular-nums text-muted-foreground">
            ${data.studio_spent_usd.toFixed(2)} / ${data.studio_budget_usd.toFixed(2)}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${Math.min(100, budgetUsed)}%`,
              background: budgetUsed > 80 ? "var(--warning)" : "var(--primary)",
            }}
          />
        </div>
      </section>
    </div>
  );
}
