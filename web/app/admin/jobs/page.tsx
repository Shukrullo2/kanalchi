import { getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import type { JobRunOut } from "@/lib/types";

export const revalidate = 0;

export default async function JobsPage() {
  const [jobs, t] = await Promise.all([
    apiFetch<JobRunOut[]>("/api/admin/jobs?limit=100", { admin: true }),
    getTranslations("admin"),
  ]);
  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{t("jobs")}</h1>
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th className="py-1">#</th>
            <th>Tenant</th>
            <th>Type</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Cost</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id} className="border-t">
              <td className="py-1.5">{j.id}</td>
              <td>{j.tenant_id ?? "—"}</td>
              <td>{j.type}</td>
              <td>{j.status}</td>
              <td className="max-w-md truncate text-muted-foreground">
                {j.error ?? (j.progress?.done != null ? `${j.progress.done}/${j.progress.total ?? "?"}` : j.progress?.message ?? "—")}
              </td>
              <td>{j.cost_usd ? `$${j.cost_usd.toFixed(3)}` : "—"}</td>
              <td className="text-muted-foreground">{new Date(j.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {jobs.length === 0 ? <p className="text-sm text-muted-foreground">No jobs yet.</p> : null}
    </div>
  );
}
