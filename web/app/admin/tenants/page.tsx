import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { SparkIcon } from "@/components/Icons";
import { State } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import type { AdminTenant } from "@/lib/types";

export default async function TenantsPage() {
  const [tenants, t] = await Promise.all([
    apiFetch<AdminTenant[]>("/api/admin/tenants", { admin: true }),
    getTranslations("admin"),
  ]);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 border-b pb-4">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">
          {t("tenants")}
        </h1>
        <Link href="/onboard" className="btn-primary">
          <SparkIcon size={14} />
          {t("onboard")}
        </Link>
      </div>

      {tenants.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          No channels yet. Connecting one takes a channel link, a Telegram
          account and a bot.
        </p>
      ) : (
        <ul className="rows">
          {tenants.map((x) => {
            // Posts stored against the estimate; only while the import is still running.
            const importing =
              x.channel &&
              x.channel.backfill_status !== "done" &&
              x.channel.backfill_total_estimate
                ? Math.min(
                    100,
                    Math.round(
                      (x.channel.imported / x.channel.backfill_total_estimate) *
                        100,
                    ),
                  )
                : null;
            return (
              <li key={x.id} className="row">
                <span className="row-margin">
                  <State status={x.status} />
                </span>
                <div className="row-body">
                  <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                    <Link
                      href={`/tenants/${x.id}`}
                      className="min-w-0 flex-1 hover:text-primary"
                    >
                      <span className="block truncate text-[0.9375rem] font-medium">
                        {x.domain}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {x.channel
                          ? x.channel.username
                            ? `@${x.channel.username}`
                            : x.channel.title
                          : "No channel connected"}
                      </span>
                    </Link>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {x.bot_username ? `@${x.bot_username}` : "No bot"}
                    </span>
                    <span className="chip shrink-0">{x.plan ?? "no plan"}</span>
                    {x.subscription_status === "pending" ? (
                      <span
                        className="shrink-0 text-xs"
                        style={{ color: "var(--warning)" }}
                      >
                        awaiting payment
                      </span>
                    ) : null}
                    <span className="tnum shrink-0 text-xs text-muted-foreground">
                      ${x.daily_chat_budget_usd} a day
                    </span>
                    {x.domain_verified_at ? null : (
                      <span
                        className="shrink-0 text-xs"
                        style={{ color: "var(--warning)" }}
                      >
                        DNS not verified
                      </span>
                    )}
                  </div>

                  {importing !== null ? (
                    <div className="mt-2.5 max-w-xs">
                      <div className="mb-1 flex justify-between text-[0.7rem] text-muted-foreground">
                        <span>Importing history</span>
                        <span className="tnum">{importing}%</span>
                      </div>
                      <div className="h-[3px] overflow-hidden rounded-full bg-border">
                        <div
                          className="h-full rounded-full bg-primary"
                          style={{ width: `${importing}%` }}
                        />
                      </div>
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
