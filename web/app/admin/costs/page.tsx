import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import { SpendBars } from "@/components/admin/SpendBars";
import { compactNumber } from "@/lib/format";
import type { CostsOut } from "@/lib/types";

export const revalidate = 0;

type Props = { searchParams: Promise<{ days?: string }> };

export default async function CostsPage({ searchParams }: Props) {
  const sp = await searchParams;
  const requested = Number(sp.days);
  const days = [7, 30, 90, 365].includes(requested) ? requested : 30;
  const [data, t] = await Promise.all([
    apiFetch<CostsOut>(`/api/admin/costs?days=${days}`, { admin: true }),
    getTranslations("admin"),
  ]);
  const daily = data.by_day.length ? data.total_usd / data.by_day.length : 0;

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b pb-4">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">{t("costs")}</h1>
        <div className="flex items-center gap-4 text-xs">
          {[7, 30, 90, 365].map((d) => (
            <Link
              key={d}
              href={`/costs?days=${d}`}
              className="nav-link text-xs"
              data-active={d === days}
            >
              {d === 365 ? "A year" : `${d} days`}
            </Link>
          ))}
        </div>
      </div>

      <dl className="flex flex-wrap gap-x-12 gap-y-4 py-6">
        {[
          ["Spent", `$${data.total_usd.toFixed(2)}`],
          ["Per day", `$${daily.toFixed(2)}`],
          ["Daily cap", `$${data.platform_daily_cap_usd.toFixed(0)}`],
          ["Served from cache", data.cache_hit_rate === null ? "—" : `${Math.round(data.cache_hit_rate * 100)}%`],
        ].map(([label, value]) => (
          <div key={label}>
            <dd className="stat-value">{value}</dd>
            <dt className="stat-label">{label}</dt>
          </div>
        ))}
      </dl>

      {data.cache_hit_rate !== null && data.cache_hit_rate < 0.3 ? (
        <p className="border-l-2 py-1 pl-3 text-sm" style={{ borderColor: "var(--warning)" }}>
          Less than a third of input is coming from cache. Something that changes every call has probably
          crept into a cached prompt prefix, and every call is paying full price.
        </p>
      ) : null}

      <section className="border-t py-6">
        <h2 className="mb-3 text-[0.9375rem] font-medium">Spend per day</h2>
        {data.by_day.length > 0 ? (
          <SpendBars data={data.by_day} />
        ) : (
          <p className="text-sm text-muted-foreground">
            No model calls in this period, so there is nothing to plot.
          </p>
        )}
      </section>

      <div className="grid gap-x-10 gap-y-6 border-t pt-6 sm:grid-cols-2">
        <Breakdown title="What the money went on" rows={data.by_purpose.map((r) => [r.purpose, r.usd, r.requests])} total={data.total_usd} />
        <Breakdown title="Which model" rows={data.by_model.map((r) => [r.model, r.usd, r.requests])} total={data.total_usd} />
      </div>

      <section className="mt-8 border-t pt-6">
        <h2 className="mb-2 text-[0.9375rem] font-medium">By channel</h2>
        {data.by_tenant.length === 0 ? (
          <p className="py-10 text-sm text-muted-foreground">Nothing has been spent yet.</p>
        ) : (
          <ul className="divide-y text-sm">
            {data.by_tenant.map((row) => (
              <li key={row.id} className="flex items-center gap-3 py-2.5">
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
    <section>
      <h2 className="mb-2 text-[0.9375rem] font-medium">{title}</h2>
      {rows.length === 0 ? (
        <p className="py-6 text-sm text-muted-foreground">Nothing yet.</p>
      ) : (
        <ul className="space-y-2.5 text-sm">
          {rows.map(([label, usd, requests]) => (
            <li key={label}>
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
                <span className="shrink-0 text-[0.7rem] tabular-nums text-muted-foreground">
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
