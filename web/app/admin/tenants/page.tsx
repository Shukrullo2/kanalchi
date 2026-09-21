import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { SparkIcon } from "@/components/Icons";
import { StatusDot } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import type { AdminTenant } from "@/lib/types";

export default async function TenantsPage() {
  const [tenants, t] = await Promise.all([
    apiFetch<AdminTenant[]>("/api/admin/tenants", { admin: true }),
    getTranslations("admin"),
  ]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("tenants")}</h1>
        <Link href="/onboard" className="btn-primary">
          <SparkIcon size={14} />
          {t("onboard")}
        </Link>
      </div>

      {tenants.length === 0 ? (
        <div className="card-surface p-12 text-center text-sm text-muted-foreground">No channels yet.</div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {tenants.map((x) => {
            const done = x.channel?.backfill_total_estimate
              ? Math.min(100, Math.round((x.channel.backfill_checkpoint / x.channel.backfill_total_estimate) * 100))
              : null;
            return (
              <Link key={x.id} href={`/tenants/${x.id}`} className="card-surface block p-4">
                <div className="flex items-center gap-2">
                  <StatusDot status={x.status} />
                  <span className="min-w-0 flex-1 truncate font-medium">{x.domain}</span>
                  <span className="chip">{x.status}</span>
                </div>
                <p className="mt-1 truncate text-sm text-muted-foreground">
                  {x.channel ? (x.channel.username ? `@${x.channel.username}` : x.channel.title) : "no channel yet"}
                </p>
                {done !== null ? (
                  <div className="mt-3">
                    <div className="mb-1 flex justify-between text-[0.7rem] text-muted-foreground">
                      <span>import</span>
                      <span className="tabular-nums">{done}%</span>
                    </div>
                    <div className="h-1 overflow-hidden rounded-full bg-border">
                      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${done}%` }} />
                    </div>
                  </div>
                ) : null}
                <div className="meta-row mt-3">
                  <span>{x.bot_username ? `@${x.bot_username}` : "no bot"}</span>
                  <span>${x.daily_chat_budget_usd}/day</span>
                  {x.domain_verified_at ? null : <span className="text-warning">DNS unverified</span>}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
