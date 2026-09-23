import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeftIcon, ExternalIcon } from "@/components/Icons";
import { DomainSettings } from "@/components/admin/DomainSettings";
import { MembersPanel } from "@/components/admin/MembersPanel";
import { PipelineMonitor } from "@/components/admin/PipelineMonitor";
import { StatusDot } from "@/components/admin/StatusDot";
import { TaxonomyVersions } from "@/components/admin/TaxonomyVersions";
import { TenantActions } from "@/components/admin/TenantActions";
import { apiFetchOrNull } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { AdminTenant, Checklist, JobRunOut, MemberOut, TaxonomyVersionOut } from "@/lib/types";

type Props = { params: Promise<{ id: string }> };

export const dynamic = "force-dynamic";

export default async function TenantDetail({ params }: Props) {
  const { id } = await params;
  const [tenant, checklist, jobs, members, versions] = await Promise.all([
    apiFetchOrNull<AdminTenant>(`/api/admin/tenants/${id}`, { admin: true }),
    apiFetchOrNull<Checklist>(`/api/admin/tenants/${id}/checklist`, { admin: true }),
    apiFetchOrNull<JobRunOut[]>(`/api/admin/jobs?tenant_id=${id}&limit=20`, { admin: true }),
    apiFetchOrNull<MemberOut[]>(`/api/admin/tenants/${id}/members`, { admin: true }),
    apiFetchOrNull<TaxonomyVersionOut[]>(`/api/admin/tenants/${id}/taxonomy`, { admin: true }),
  ]);
  if (!tenant) notFound();

  const activeVersion = checklist?.pipeline?.stages.taxonomy.done
    ? (versions ?? []).find((v) => v.status === "applied")?.id ?? null
    : null;

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
          <span className="ml-auto flex items-center gap-4">
            <Link href={`/tenants/${tenant.id}/index`} className="link-quiet text-sm">
              Index →
            </Link>
            <a
              href={`https://${tenant.domain}`}
              target="_blank"
              rel="noreferrer"
              className="link-quiet flex items-center gap-1 text-sm"
            >
              open blog <ExternalIcon size={12} />
            </a>
          </span>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {[
          ["Channel", tenant.channel ? (tenant.channel.username ? `@${tenant.channel.username}` : tenant.channel.title) : "—"],
          ["Subscribers", tenant.channel?.participants_count ? compactNumber(tenant.channel.participants_count) : "—"],
          ["Bot", tenant.bot_username ? `@${tenant.bot_username}` : "none (platform bot signs in)"],
          ["Domain", tenant.auto_domain ? "platform domain" : tenant.domain_verified_at ? "own, verified" : "own, unverified"],
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

      {tenant.channel ? (
        <PipelineMonitor tenantId={tenant.id} initial={checklist} />
      ) : (
        <p className="card-surface p-4 text-sm text-muted-foreground">
          No channel attached yet.{" "}
          <Link href={`/onboard?tenant=${tenant.id}`} className="underline">
            Continue onboarding
          </Link>
          .
        </p>
      )}

      <TenantActions tenant={tenant} />

      <div className="grid gap-4 lg:grid-cols-2">
        <DomainSettings tenant={tenant} dnsDetail={checklist?.steps.domain.detail ?? null} />
        <MembersPanel tenantId={tenant.id} initial={members ?? []} />
      </div>

      <TaxonomyVersions tenantId={tenant.id} versions={versions ?? []} activeId={activeVersion} />

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
                      : (j.progress?.message ?? j.progress?.stage ?? "—"))}
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
