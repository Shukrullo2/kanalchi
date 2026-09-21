import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { ChartIcon, SparkIcon } from "@/components/Icons";
import { StatusDot } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { AdminOverview } from "@/lib/types";

export default async function AdminHome() {
  const [data, t] = await Promise.all([
    apiFetch<AdminOverview>("/api/admin/overview", { admin: true }),
    getTranslations("admin"),
  ]);

  return (
    <div className="space-y-6">
      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          [t("tenants"), compactNumber(data.tenants.length)],
          [t("accounts"), compactNumber(data.accounts)],
          [t("runningJobs"), compactNumber(data.running_jobs)],
          [t("spendToday"), `$${data.spend_today_usd.toFixed(2)}`],
        ].map(([label, value]) => (
          <div key={label} className="stat-tile">
            <dt className="stat-label">{label}</dt>
            <dd className="stat-value">{value}</dd>
          </div>
        ))}
      </dl>

      <section className="card-surface overflow-hidden">
        <header className="flex items-center justify-between gap-3 border-b px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-medium">
            <ChartIcon size={15} className="text-muted-foreground" />
            {t("tenants")}
          </h2>
          <Link href="/onboard" className="link-quiet flex items-center gap-1 text-xs">
            <SparkIcon size={12} />
            {t("onboard")}
          </Link>
        </header>

        {data.tenants.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">
            No channels yet.{" "}
            <Link href="/onboard" className="text-primary underline">
              {t("onboard")}
            </Link>
          </div>
        ) : (
          <ul className="divide-y">
            {data.tenants.map((x) => (
              <li key={x.id}>
                <Link
                  href={`/tenants/${x.id}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-surface-2"
                >
                  <StatusDot status={x.status} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{x.domain}</span>
                    <span className="block truncate text-xs text-muted-foreground">{x.title || "—"}</span>
                  </span>
                  <span className="hidden text-xs text-muted-foreground sm:block">
                    {x.bot_username ? `@${x.bot_username}` : "no bot"}
                  </span>
                  <span className="chip">{x.status}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
