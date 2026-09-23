"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { patch, post } from "@/lib/client";
import type { AdminTenant } from "@/lib/types";

export function TenantActions({ tenant }: { tenant: AdminTenant }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      setMsg(`${label}: ok`);
      router.refresh();
    } catch (e) {
      setMsg(`${label}: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  const paused = tenant.status === "paused";
  const imported = tenant.channel?.backfill_status === "done";
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      {imported ? (
        <button
          disabled={busy || paused}
          onClick={() => void run("catch up", () => post(`/api/admin/tenants/${tenant.id}/start`))}
          className="btn-ghost"
          title="Reads anything posted since the last import."
        >
          Catch up history
        </button>
      ) : null}
      <button
        disabled={busy || paused || !tenant.channel}
        onClick={() => void run("resync", () => post(`/api/admin/tenants/${tenant.id}/resync?days=30`))}
        className="btn-ghost"
        title="Re-reads the last 30 days for edits, deletions and view counts."
      >
        Resync 30d
      </button>
      <button
        disabled={busy}
        onClick={() =>
          void run(paused ? "resume" : "pause", () =>
            patch(`/api/admin/tenants/${tenant.id}`, { status: paused ? "active" : "paused" }),
          )
        }
        className="btn-ghost"
        title="Paused: the assistant, imports and every background job stop; the site stays up and readable."
      >
        {paused ? "Resume channel" : "Pause channel"}
      </button>
      {paused ? (
        <span className="text-xs" style={{ color: "var(--warning)" }}>
          Paused: nothing spends or runs for this channel; readers can still browse.
        </span>
      ) : null}
      {msg ? <span className="text-muted-foreground">{msg}</span> : null}
    </div>
  );
}
