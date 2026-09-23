"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { patch, post } from "@/lib/client";
import type { AdminTenant } from "@/lib/types";

/**
 * A channel starts life under the platform domain; a domain of its own is optional and can
 * be set any time. Setting one resets verification, since it has to be pointed at the server.
 */
export function DomainSettings({ tenant, dnsDetail }: { tenant: AdminTenant; dnsDetail: string | null }) {
  const router = useRouter();
  const [domain, setDomain] = useState(tenant.auto_domain ? "" : tenant.domain);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setNote(null);
    try {
      const out = (await fn()) as { detail?: string } | undefined;
      setNote(out?.detail ? `${label}: ${out.detail}` : `${label}: ok`);
      router.refresh();
    } catch (e) {
      setNote(`${label}: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-surface p-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-sm font-medium">Domain</h2>
        <span className="text-sm">{tenant.domain}</span>
        <span className="chip">{tenant.auto_domain ? "platform domain" : tenant.domain_verified_at ? "verified" : "unverified"}</span>
      </div>
      <p className="mt-0.5 text-xs text-muted-foreground">
        {tenant.auto_domain
          ? "The blog is live at this address already. A domain of the channel's own is optional."
          : (dnsDetail ?? "Point an A record at the server, then check.")}
      </p>
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run("domain", () => patch(`/api/admin/tenants/${tenant.id}`, { domain: domain.trim() }));
        }}
      >
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">Custom domain</span>
          <input
            className="input-field w-64"
            placeholder="blog.example.uz"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          />
        </label>
        <button disabled={busy || domain.trim().length < 3 || domain.trim() === tenant.domain} className="btn-ghost">
          Set domain
        </button>
        {!tenant.auto_domain ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => void run("dns", () => post(`/api/admin/tenants/${tenant.id}/verify-domain`))}
            className="btn-ghost"
          >
            Check DNS
          </button>
        ) : null}
        {note ? <span className="basis-full text-xs text-muted-foreground">{note}</span> : null}
      </form>
    </section>
  );
}
