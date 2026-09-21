import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import type { AdminTenant } from "@/lib/types";

export default async function TenantsPage() {
  const [tenants, t] = await Promise.all([
    apiFetch<AdminTenant[]>("/api/admin/tenants", { admin: true }),
    getTranslations("admin"),
  ]);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">{t("tenants")}</h1>
        <Link href="/onboard" className="rounded bg-foreground px-3 py-1 text-sm text-background">
          {t("onboard")}
        </Link>
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th className="py-1">Domain</th>
            <th>Channel</th>
            <th>Status</th>
            <th>Import</th>
            <th>Bot</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((x) => (
            <tr key={x.id} className="border-t">
              <td className="py-2">
                <Link href={`/tenants/${x.id}`} className="underline">
                  {x.domain}
                </Link>
              </td>
              <td>{x.channel ? (x.channel.username ? `@${x.channel.username}` : x.channel.title) : "—"}</td>
              <td>{x.status}</td>
              <td className="text-muted-foreground">
                {x.channel ? `${x.channel.backfill_status} ${x.channel.backfill_checkpoint}/${x.channel.backfill_total_estimate ?? "?"}` : "—"}
              </td>
              <td>{x.bot_username ? `@${x.bot_username}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {tenants.length === 0 ? <p className="text-sm text-muted-foreground">No channels yet.</p> : null}
    </div>
  );
}
