import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import type { AdminOverview } from "@/lib/types";

export default async function AdminHome() {
  const [data, t] = await Promise.all([apiFetch<AdminOverview>("/api/admin/overview", { admin: true }), getTranslations("admin")]);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Stat label={t("tenants")} value={data.tenants.length} />
        <Stat label={t("accounts")} value={data.accounts} />
        <Stat label={t("runningJobs")} value={data.running_jobs} />
        <Stat label={t("spendToday")} value={`$${data.spend_today_usd.toFixed(2)}`} />
      </div>
      <section>
        <h2 className="mb-2 font-medium">{t("tenants")}</h2>
        {data.tenants.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            <Link href="/onboard" className="underline">
              {t("onboard")}
            </Link>
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1">Domain</th>
                <th>Title</th>
                <th>Status</th>
                <th>Bot</th>
              </tr>
            </thead>
            <tbody>
              {data.tenants.map((x) => (
                <tr key={x.id} className="border-t">
                  <td className="py-2">
                    <Link href={`/tenants/${x.id}`} className="underline">
                      {x.domain}
                    </Link>
                  </td>
                  <td>{x.title}</td>
                  <td>{x.status}</td>
                  <td>{x.bot_username ? `@${x.bot_username}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
    </div>
  );
}
