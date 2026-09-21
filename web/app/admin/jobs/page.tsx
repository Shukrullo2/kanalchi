import { getTranslations } from "next-intl/server";
import { StatusDot } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import type { JobRunOut } from "@/lib/types";

export const revalidate = 0;

export default async function JobsPage() {
  const [jobs, t] = await Promise.all([
    apiFetch<JobRunOut[]>("/api/admin/jobs?limit=100", { admin: true }),
    getTranslations("admin"),
  ]);

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">{t("jobs")}</h1>
      {jobs.length === 0 ? (
        <div className="card-surface p-12 text-center text-sm text-muted-foreground">No jobs yet.</div>
      ) : (
        <div className="card-surface overflow-hidden">
          <ul className="divide-y text-sm">
            {jobs.map((j) => (
              <li key={j.id} className="flex items-center gap-3 px-4 py-2.5">
                <StatusDot status={j.status} />
                <span className="w-10 shrink-0 text-xs tabular-nums text-muted-foreground">#{j.id}</span>
                <span className="w-24 shrink-0 font-medium">{j.type}</span>
                <span className="w-12 shrink-0 text-xs text-muted-foreground">
                  {j.tenant_id ? `t${j.tenant_id}` : "—"}
                </span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">
                  {j.error ??
                    (j.progress?.done != null
                      ? `${j.progress.done}/${j.progress.total ?? "?"}`
                      : (j.progress?.message ?? "—"))}
                </span>
                {j.cost_usd ? <span className="shrink-0 text-xs tabular-nums">${j.cost_usd.toFixed(3)}</span> : null}
                <span className="hidden shrink-0 text-xs text-muted-foreground sm:block">
                  {new Date(j.created_at).toISOString().slice(5, 16).replace("T", " ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
