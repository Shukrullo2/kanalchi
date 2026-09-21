import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeftIcon, ExternalIcon } from "@/components/Icons";
import { StatusDot } from "@/components/admin/StatusDot";
import { TenantActions } from "@/components/admin/TenantActions";
import { apiFetchOrNull } from "@/lib/api";
import type { AdminTenant, Checklist, JobRunOut } from "@/lib/types";
import { compactNumber } from "@/lib/format";

type Props = { params: Promise<{ id: string }> };

export default async function TenantDetail({ params }: Props) {
  const { id } = await params;
  const [tenant, checklist, jobs] = await Promise.all([
    apiFetchOrNull<AdminTenant>(`/api/admin/tenants/${id}`, { admin: true }),
    apiFetchOrNull<Checklist>(`/api/admin/tenants/${id}/checklist`, { admin: true }),
    apiFetchOrNull<JobRunOut[]>(`/api/admin/jobs?tenant_id=${id}&limit=20`, { admin: true }),
  ]);
  if (!tenant) notFound();

  const backfill = checklist?.steps.backfill;
  const done = backfill?.total ? Math.min(100, Math.round((backfill.checkpoint / backfill.total) * 100)) : null;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/tenants" className="link-quiet mb-2 inline-flex items-center gap-1.5 text-sm">
          <ArrowLeftIcon size={14} /> channels
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <StatusDot status={tenant.status} />
          <h1 className="text-xl font-semibold tracking-tight">{tenant.domain}</h1>
          <span className="chip">{tenant.status}</span>
          <a
            href={`https://${tenant.domain}`}
            target="_blank"
            rel="noreferrer"
            className="link-quiet ml-auto flex items-center gap-1 text-sm"
          >
            open blog <ExternalIcon size={12} />
          </a>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          ["Channel", tenant.channel ? (tenant.channel.username ? `@${tenant.channel.username}` : tenant.channel.title) : "—"],
          ["Subscribers", tenant.channel?.participants_count ? compactNumber(tenant.channel.participants_count) : "—"],
          ["Bot", tenant.bot_username ? `@${tenant.bot_username}` : "—"],
          ["DNS", tenant.domain_verified_at ? "verified" : "unverified"],
          ["Chat budget", `$${tenant.daily_chat_budget_usd}/day`],
          ["Studio budget", `$${tenant.daily_studio_budget_usd}/day`],
          ["Languages", tenant.locales.join(", ")],
          ["Created", new Date(tenant.created_at).toISOString().slice(0, 10)],
        ].map(([label, value]) => (
          <div key={label} className="stat-tile">
            <dt className="stat-label">{label}</dt>
            <dd className="truncate text-sm font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      {done !== null ? (
        <section className="card-surface p-4">
          <div className="mb-2 flex items-baseline justify-between text-sm">
            <span className="font-medium">History import</span>
            <span className="text-muted-foreground tabular-nums">
              {backfill?.checkpoint} / {backfill?.total} · {done}%
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-border">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${done}%` }} />
          </div>
        </section>
      ) : null}

      <TenantActions tenant={tenant} />

      <section className="card-surface overflow-hidden">
        <h2 className="border-b px-4 py-3 text-sm font-medium">Recent jobs</h2>
        {jobs && jobs.length > 0 ? (
          <ul className="divide-y text-sm">
            {jobs.map((j) => (
              <li key={j.id} className="flex items-center gap-3 px-4 py-2.5">
                <StatusDot status={j.status} />
                <span className="w-24 shrink-0 font-medium">{j.type}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {j.error ??
                    (j.progress?.done != null
                      ? `${j.progress.done}/${j.progress.total ?? "?"}`
                      : (j.progress?.message ?? "—"))}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {j.started_at ? new Date(j.started_at).toISOString().slice(5, 16).replace("T", " ") : "—"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="p-8 text-center text-sm text-muted-foreground">No jobs yet.</p>
        )}
      </section>
    </div>
  );
}
