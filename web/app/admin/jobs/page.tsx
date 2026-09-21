import { getTranslations } from "next-intl/server";
import { State } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import type { JobRunOut } from "@/lib/types";

export const revalidate = 0;

export default async function JobsPage() {
  const [jobs, t] = await Promise.all([
    apiFetch<JobRunOut[]>("/api/admin/jobs?limit=100", { admin: true }),
    getTranslations("admin"),
  ]);

  return (
    <div>
      <header className="border-b pb-4">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">{t("jobs")}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          The hundred most recent runs. Long work is a chain of short jobs, so one import shows up here many times.
        </p>
      </header>

      {jobs.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Nothing has run yet. Jobs appear as soon as a channel starts importing.
        </p>
      ) : (
        <ul className="rows">
          {jobs.map((j) => (
            <li key={j.id} className="row" style={{ "--state-w": "9rem" } as React.CSSProperties}>
              <span className="row-margin">
                <State status={j.status} />
                <span>{clock(j.created_at)}</span>
              </span>
              <span className="row-body flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <span className="w-32 shrink-0 text-[0.9375rem]">{j.type.replace(/_/g, " ")}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                  {j.error ? (
                    <span style={{ color: "var(--destructive)" }}>{j.error}</span>
                  ) : j.progress?.done != null ? (
                    `${j.progress.done} of ${j.progress.total ?? "?"}`
                  ) : (
                    (j.progress?.message ?? "")
                  )}
                </span>
                {j.tenant_id ? (
                  <span className="shrink-0 text-xs text-muted-foreground">channel {j.tenant_id}</span>
                ) : null}
                {j.cost_usd ? (
                  <span className="tnum shrink-0 text-xs">${j.cost_usd.toFixed(3)}</span>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** UTC, written the same on the server and in the browser. */
function clock(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}
