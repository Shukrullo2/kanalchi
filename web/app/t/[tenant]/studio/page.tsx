import Link from "next/link";
import { ArrowRightIcon } from "@/components/Icons";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { StudioOverview } from "@/lib/types";

export default async function StudioDashboard() {
  const data = await apiFetch<StudioOverview>("/api/studio/overview");
  const budgetUsed = data.studio_budget_usd ? (data.studio_spent_usd / data.studio_budget_usd) * 100 : 0;

  // Things worth acting on, gathered into one list instead of one card each.
  const prompts = [
    data.pending_tags > 0 && {
      href: "/studio/tags",
      title: `${data.pending_tags} names are waiting to be filed`,
      body: "They keep coming up in your posts but are not in the index yet.",
    },
    !data.has_voice_profile && {
      href: "/studio/settings",
      title: "Teach the assistant how you write",
      body: "It reads your own posts once, and drafts start sounding like you.",
    },
  ].filter(Boolean) as { href: string; title: string; body: string }[];

  return (
    <div>
      <dl className="flex flex-wrap gap-x-10 gap-y-4 pb-6">
        {[
          ["Posts", compactNumber(data.posts)],
          ["Subscribers", data.subscribers ? compactNumber(data.subscribers) : "—"],
          ["Drafts", String(data.drafts.draft ?? 0)],
          ["Scheduled", String(data.drafts.scheduled ?? 0)],
        ].map(([label, value]) => (
          <div key={label}>
            <dd className="stat-value">{value}</dd>
            <dt className="stat-label">{label}</dt>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-2 border-t pt-6">
        <Link href="/studio/drafts" className="btn-primary">
          Write a post
        </Link>
        <Link href="/studio/research" className="btn-ghost">
          Research the archive
        </Link>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {data.bot_username
          ? `Posts go out through @${data.bot_username}.`
          : "Connect a bot in settings before you can publish."}
      </p>

      {prompts.length > 0 ? (
        <ul className="mt-8 divide-y border-y">
          {prompts.map((p) => (
            <li key={p.href}>
              <Link href={p.href} className="flex items-center gap-4 py-4">
                <span className="min-w-0 flex-1">
                  <span className="block text-[0.9375rem] font-medium">{p.title}</span>
                  <span className="mt-0.5 block text-sm text-muted-foreground">{p.body}</span>
                </span>
                <ArrowRightIcon size={15} className="shrink-0 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      <section className="mt-8 max-w-sm">
        <div className="mb-1.5 flex items-baseline justify-between text-sm">
          <span className="text-muted-foreground">Assistant spend today</span>
          <span className="tnum">
            ${data.studio_spent_usd.toFixed(2)} / ${data.studio_budget_usd.toFixed(2)}
          </span>
        </div>
        <div className="h-[3px] overflow-hidden rounded-full bg-border">
          <div
            className="h-full rounded-full"
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
