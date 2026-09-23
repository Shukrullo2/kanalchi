import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { State } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { AdminOverview } from "@/lib/types";

export default async function AdminHome() {
  const [data, t] = await Promise.all([
    apiFetch<AdminOverview>("/api/admin/overview", { admin: true }),
    getTranslations("admin"),
  ]);

  return (
    <div>
      <dl className="flex flex-wrap gap-x-12 gap-y-4 border-b pb-6">
        {[
          [t("tenants"), compactNumber(data.tenants.length)],
          [t("accounts"), compactNumber(data.accounts)],
          [t("runningJobs"), compactNumber(data.running_jobs)],
          [t("spendToday"), `$${data.spend_today_usd.toFixed(2)}`],
        ].map(([label, value]) => (
          <div key={label}>
            <dd className="stat-value">{value}</dd>
            <dt className="stat-label">{label}</dt>
          </div>
        ))}
      </dl>

      <section className="mt-7">
        <header className="flex items-baseline justify-between gap-3 border-b pb-2.5">
          <h2 className="text-[0.9375rem] font-medium">{t("tenants")}</h2>
          <Link href="/onboard" className="link-quiet text-xs">
            {t("onboard")}
          </Link>
        </header>

        {data.tenants.length === 0 ? (
          <p className="py-14 text-center text-sm text-muted-foreground">
            No channels yet.{" "}
            <Link href="/onboard" className="text-primary underline">
              Connect the first one
            </Link>
            .
          </p>
        ) : (
          <ul className="rows">
            {data.tenants.map((x) => (
              <li key={x.id} className="row">
                <span className="row-margin">
                  <State status={x.status} />
                </span>
                <span className="row-body flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <Link href={`/tenants/${x.id}`} className="min-w-0 flex-1 hover:text-primary">
                    <span className="block truncate text-[0.9375rem] font-medium">{x.domain}</span>
                    <span className="block truncate text-xs text-muted-foreground">{x.title || "No title yet"}</span>
                  </Link>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {x.bot_username ? `@${x.bot_username}` : "No bot connected"}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
