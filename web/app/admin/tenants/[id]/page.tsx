import Link from "next/link";
import { notFound } from "next/navigation";
import { TenantActions } from "@/components/admin/TenantActions";
import { apiFetchOrNull } from "@/lib/api";
import type { AdminTenant, Checklist, JobRunOut } from "@/lib/types";

type Props = { params: Promise<{ id: string }> };

export default async function TenantDetail({ params }: Props) {
  const { id } = await params;
  const [tenant, checklist, jobs] = await Promise.all([
    apiFetchOrNull<AdminTenant>(`/api/admin/tenants/${id}`, { admin: true }),
    apiFetchOrNull<Checklist>(`/api/admin/tenants/${id}/checklist`, { admin: true }),
    apiFetchOrNull<JobRunOut[]>(`/api/admin/jobs?tenant_id=${id}&limit=20`, { admin: true }),
  ]);
  if (!tenant) notFound();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="text-lg font-semibold">{tenant.domain}</h1>
        <span className="rounded bg-muted px-2 py-0.5 text-xs">{tenant.status}</span>
        <a href={`https://${tenant.domain}`} target="_blank" rel="noreferrer" className="text-sm underline">
          open blog ↗
        </a>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Field label="Channel" value={tenant.channel ? (tenant.channel.username ? `@${tenant.channel.username}` : tenant.channel.title) : "—"} />
        <Field label="Subscribers" value={tenant.channel?.participants_count ?? "—"} />
        <Field label="Bot" value={tenant.bot_username ? `@${tenant.bot_username}` : "—"} />
        <Field label="DNS verified" value={tenant.domain_verified_at ? new Date(tenant.domain_verified_at).toLocaleDateString() : "no"} />
        <Field
          label="Import"
          value={checklist ? `${checklist.steps.backfill.status ?? "—"} ${checklist.steps.backfill.checkpoint}/${checklist.steps.backfill.total ?? "?"}` : "—"}
        />
        <Field label="Chat budget" value={`$${tenant.daily_chat_budget_usd}/day`} />
        <Field label="Studio budget" value={`$${tenant.daily_studio_budget_usd}/day`} />
        <Field label="Languages" value={tenant.locales.join(", ")} />
      </dl>

      <TenantActions tenant={tenant} />

      <section>
        <h2 className="mb-2 font-medium">Recent jobs</h2>
        {jobs && jobs.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
              <tr>
                <th className="py-1">Type</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-t">
                  <td className="py-1.5">{j.type}</td>
                  <td>{j.status}</td>
                  <td className="text-muted-foreground">
                    {j.error ?? (j.progress?.done != null ? `${j.progress.done}/${j.progress.total ?? "?"}` : j.progress?.message ?? "—")}
                  </td>
                  <td className="text-muted-foreground">{j.started_at ? new Date(j.started_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground">No jobs yet.</p>
        )}
      </section>

      <Link href="/tenants" className="inline-block text-sm underline">
        ← all channels
      </Link>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded border p-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
