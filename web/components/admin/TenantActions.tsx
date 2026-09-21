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
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <button
        disabled={busy}
        onClick={() => void run("import", () => post(`/api/admin/tenants/${tenant.id}/start`))}
        className="btn-ghost"
      >
        Resume import
      </button>
      <button
        disabled={busy}
        onClick={() => void run("resync", () => post(`/api/admin/tenants/${tenant.id}/resync?days=30`))}
        className="btn-ghost"
      >
        Resync 30d
      </button>
      <button
        disabled={busy}
        onClick={() => void run("dns", () => post(`/api/admin/tenants/${tenant.id}/verify-domain`))}
        className="btn-ghost"
      >
        Check DNS
      </button>
      <button
        disabled={busy}
        onClick={() => void run(paused ? "resume" : "pause", () => patch(`/api/admin/tenants/${tenant.id}`, { status: paused ? "active" : "paused" }))}
        className="btn-ghost"
      >
        {paused ? "Resume channel" : "Pause channel"}
      </button>
      {msg ? <span className="text-muted-foreground">{msg}</span> : null}
    </div>
  );
}
