"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { patch } from "@/lib/client";
import { uzs } from "@/lib/format";
import type { AdminTenant, PlanId, SubscriptionStatus } from "@/lib/types";

const PLANS: PlanId[] = ["archive", "basic", "premium"];
const STATUSES: SubscriptionStatus[] = [
  "none",
  "pending",
  "active",
  "past_due",
  "cancelled",
];

/**
 * Plan, subscription and the onboarding payment, all set by hand: money changes hands on
 * Telegram, and this is where the admin writes down that it did.
 */
export function BillingPanel({ tenant }: { tenant: AdminTenant }) {
  const router = useRouter();
  const [plan, setPlan] = useState<PlanId | "">(tenant.plan ?? "");
  const [status, setStatus] = useState<SubscriptionStatus>(
    tenant.subscription_status,
  );
  const [until, setUntil] = useState(tenant.subscription_paid_until ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function save(extra: Record<string, unknown> = {}) {
    setBusy(true);
    setMsg(null);
    try {
      await patch(`/api/admin/tenants/${tenant.id}`, {
        ...(plan ? { plan } : {}),
        subscription_status: status,
        ...(until ? { subscription_paid_until: until } : {}),
        ...extra,
      });
      setMsg("saved");
      router.refresh();
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const quote = tenant.onboarding_quote;
  return (
    <section className="card-surface overflow-hidden">
      <h2 className="border-b px-4 py-3 text-sm font-medium">
        Billing{" "}
        <span className="text-xs font-normal text-muted-foreground">
          {tenant.source === "self"
            ? "registered by the blogger"
            : "connected by an admin"}
        </span>
      </h2>
      <div className="grid gap-4 p-4 text-sm sm:grid-cols-2">
        <div>
          <div className="stat-label">Onboarding</div>
          {quote ? (
            <p className="mt-1">
              <span className="tnum font-medium">
                {uzs(quote.price_uzs)} UZS
              </span>{" "}
              <span className="text-muted-foreground">
                for {quote.posts.toLocaleString("en-US")} posts ({quote.source}
                {quote.avg_post_tokens
                  ? `, ${quote.avg_post_tokens} tok/post`
                  : ""}
                ; AI ≈ ${quote.ai_usd})
              </span>
            </p>
          ) : (
            <p className="mt-1 text-muted-foreground">No quote yet.</p>
          )}
          {tenant.requested_at ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Requested{" "}
              {new Date(tenant.requested_at)
                .toISOString()
                .slice(0, 16)
                .replace("T", " ")}
            </p>
          ) : null}
          <button
            className="btn-ghost mt-2"
            disabled={busy}
            onClick={() =>
              void save({ onboarding_paid: !tenant.onboarding_paid_at })
            }
          >
            {tenant.onboarding_paid_at
              ? `Paid ${new Date(tenant.onboarding_paid_at).toISOString().slice(0, 10)} · mark unpaid`
              : "Mark onboarding paid"}
          </button>
        </div>

        <div className="space-y-2">
          <label className="flex items-center gap-3">
            <span className="w-24 text-muted-foreground">Plan</span>
            <select
              className="input-field"
              value={plan}
              onChange={(e) => setPlan(e.target.value as PlanId | "")}
            >
              <option value="">not chosen</option>
              {PLANS.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-3">
            <span className="w-24 text-muted-foreground">Subscription</span>
            <select
              className="input-field"
              value={status}
              onChange={(e) => setStatus(e.target.value as SubscriptionStatus)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-3">
            <span className="w-24 text-muted-foreground">Paid until</span>
            <input
              className="input-field"
              type="date"
              value={until}
              onChange={(e) => setUntil(e.target.value)}
            />
          </label>
          <div className="flex items-center gap-3 pt-1">
            <button
              className="btn-primary py-1.5 text-xs"
              disabled={busy}
              onClick={() => void save()}
            >
              Save
            </button>
            {msg ? (
              <span className="text-xs text-muted-foreground">{msg}</span>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}
