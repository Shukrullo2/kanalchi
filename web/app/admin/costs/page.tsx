import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import { compactNumber, monthLabel } from "@/lib/format";
import type { CostsOut } from "@/lib/types";

export const revalidate = 0;

type Props = { searchParams: Promise<{ days?: string }> };

export default async function CostsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const days = Number(sp.days ?? 30);
  const [data, t] = await Promise.all([
    apiFetch<CostsOut>(`/api/admin/costs?days=${days}`, { admin: true }),
    getTranslations("admin"),
  ]);
  const max = Math.max(0.0001, ...data.by_day.map((d) => d.usd));
  const daily = data.by_day.length ? data.total_usd / data.by_day.length : 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("costs")}</h1>
        <div className="flex items-center rounded-full bg-surface-2 p-0.5 text-xs">
          {[7, 30, 90, 365].map((d) => (
            <Link
              key={d}
              href={`/costs?days=${d}`}
              className={`rounded-full px-2.5 py-1 transition-colors ${
                d === days ? "bg-surface font-medium shadow-xs" : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {d}d
            </Link>
          ))}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          ["Total", `$${data.total_usd.toFixed(2)}`],
          ["Average per day", `$${daily.toFixed(2)}`],
          ["Daily cap", `$${data.platform_daily_cap_usd.toFixed(0)}`],
          ["Cache hit rate", data.cache_hit_rate === null ? "—" : `${Math.round(data.cache_hit_rate * 100)}%`],
        ].map(([label, value]) => (
          <div key={label} className="stat-tile">
            <dt className="stat-label">{label}</dt>
            <dd className="stat-value">{value}</dd>
          </div>
        ))}
      </dl>

      {data.cache_hit_rate !== null && data.cache_hit_rate < 0.3 ? (
        <p className="rounded-lg border p-3 text-sm" style={{ borderColor: "var(--warning)", color: "var(--warning)" }}>
          Cache hit rate is low. Something volatile is probably sitting in a cached prompt prefix.
        </p>
      ) : null}

      <section className="card-surface p-4">
        <h2 className="mb-3 text-sm font-medium">Spend per day</h2>
        <div className="flex h-24 items-end gap-[2px]">
          {data.by_day.map((d) => (
            <div
              key={d.day}
              className="group relative min-w-[3px] flex-1 rounded-sm bg-primary/70 transition-colors hover:bg-primary"
              style={{ height: `${Math.max(3, (d.usd / max) * 96)}px` }}
              title={`${d.day}: $${d.usd.toFixed(3)}`}
            />
          ))}
        </div>
        {data.by_day.length > 1 ? (
          <div className="mt-1 flex justify-between text-[0.65rem] text-muted-foreground">
            <span>{monthLabel(data.by_day[0].day.slice(0, 7))}</span>
            <span>{monthLabel(data.by_day[data.by_day.length - 1].day.slice(0, 7))}</span>
          </div>
        ) : null}
      </section>

      <div className="grid gap-3 sm:grid-cols-2">
        <Breakdown title="By purpose" rows={data.by_purpose.map((r) => [r.purpose, r.usd, r.requests])} total={data.total_usd} />
        <Breakdown title="By model" rows={data.by_model.map((r) => [r.model, r.usd, r.requests])} total={data.total_usd} />
      </div>

      <section className="card-surface overflow-hidden">
        <h2 className="border-b px-4 py-3 text-sm font-medium">By channel</h2>
        {data.by_tenant.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No spend recorded yet.</p>
        ) : (
          <ul className="divide-y text-sm">
            {data.by_tenant.map((row) => (
              <li key={row.id} className="flex items-center gap-3 px-4 py-2.5">
                <Link href={`/tenants/${row.id}`} className="min-w-0 flex-1 truncate hover:text-primary">
                  {row.domain}
                </Link>
                <span className="tabular-nums">${row.usd.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Breakdown({ title, rows, total }: { title: string; rows: [string, number, number][]; total: number }) {
  return (
    <section className="card-surface overflow-hidden">
      <h2 className="border-b px-4 py-3 text-sm font-medium">{title}</h2>
      {rows.length === 0 ? (
        <p className="p-6 text-center text-sm text-muted-foreground">Nothing yet.</p>
      ) : (
        <ul className="divide-y text-sm">
          {rows.map(([label, usd, requests]) => (
            <li key={label} className="px-4 py-2.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate">{label.replace(/_/g, " ")}</span>
                <span className="shrink-0 tabular-nums">${usd.toFixed(2)}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-border">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${total ? (usd / total) * 100 : 0}%` }}
                  />
                </div>
                <span className="shrink-0 text-[0.65rem] tabular-nums text-muted-foreground">
                  {compactNumber(requests)} calls
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
