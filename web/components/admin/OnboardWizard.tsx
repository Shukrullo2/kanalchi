"use client";

import { useEffect, useState } from "react";
import { call, post } from "@/lib/client";
import type { AdminTenant, Checklist, TgAccount } from "@/lib/types";

type BotResult = { bot_username: string; webhook_set: boolean; webhook_error: string | null; setdomain_hint: string };

/**
 * Connecting a channel really is a sequence — each step needs the one before it —
 * so the numbers are information and they sit in the margin, the way the date
 * does on the reading side. A finished step swaps its number for a tick.
 */
function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: React.ReactNode }) {
  return (
    <section className="row" style={{ "--state-w": "5rem" } as React.CSSProperties}>
      <div className="row-margin">
        <span
          className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-semibold"
          style={
            done
              ? { background: "var(--success)", color: "var(--background)" }
              : { background: "var(--surface-2)", color: "var(--muted-foreground)" }
          }
          aria-hidden
        >
          {done ? "✓" : n}
        </span>
      </div>
      <div className="row-body">
        <h2 className="mb-3 text-[0.9375rem] font-medium">
          {title}
          <span className="sr-only">{done ? " — done" : " — not done yet"}</span>
        </h2>
        {children}
      </div>
    </section>
  );
}

export function OnboardWizard({ accounts }: { accounts: TgAccount[] }) {
  const [tenant, setTenant] = useState<AdminTenant | null>(null);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ domain: "", title: "", link: "", accountId: accounts[0]?.id ?? 0, joinPrivate: false, token: "" });
  const [botResult, setBotResult] = useState<BotResult | null>(null);

  const activeAccounts = accounts.filter((a) => a.status === "active");

  async function refresh(id: number) {
    setChecklist(await call<Checklist>(`/api/admin/tenants/${id}/checklist`));
  }

  useEffect(() => {
    if (!tenant) return;
    const id = setInterval(() => void refresh(tenant.id), 3000);
    return () => clearInterval(id);
  }, [tenant]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      if (tenant) await refresh(tenant.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const steps = checklist?.steps;

  return (
    <div className="rows max-w-2xl">
      {error ? (
        <p className="border-l-2 py-1 pl-3 text-sm" style={{ color: "var(--destructive)", borderColor: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}

      <Step n={1} title="Domain" done={!!tenant}>
        {tenant ? (
          <p className="text-sm text-muted-foreground">
            {tenant.domain} · tenant #{tenant.id}
          </p>
        ) : (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                const t = await post<AdminTenant>("/api/admin/tenants", { domain: form.domain, title: form.title });
                setTenant(t);
                setChecklist(await call<Checklist>(`/api/admin/tenants/${t.id}/checklist`));
              });
            }}
          >
            <label className="text-sm">
              <span className="mb-1 block text-muted-foreground">Blog domain</span>
              <input
                className="input-field w-56"
                placeholder="blog.example.uz"
                value={form.domain}
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted-foreground">Title (optional)</span>
              <input
                className="input-field w-48"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <button disabled={busy || form.domain.length < 3} className="btn-primary">
              Create
            </button>
          </form>
        )}
      </Step>

      <Step n={2} title="Channel" done={!!steps?.channel.done}>
        {steps?.channel.done ? (
          <p className="text-sm text-muted-foreground">
            {steps.channel.title} {steps.channel.username ? `(@${steps.channel.username})` : "(private)"} ·{" "}
            {steps.channel.total ?? "?"} posts{steps.channel.noforwards ? " · protected content: media stays on Telegram" : ""}
          </p>
        ) : (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run(() =>
                post(`/api/admin/tenants/${tenant!.id}/channel`, {
                  link: form.link,
                  account_id: Number(form.accountId),
                  allow_join_private: form.joinPrivate,
                }),
              );
            }}
          >
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Channel link or @username</span>
                <input
                  className="input-field w-64"
                  placeholder="https://t.me/mychannel"
                  value={form.link}
                  onChange={(e) => setForm({ ...form, link: e.target.value })}
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Telegram account</span>
                <select
                  className="input-field w-auto"
                  value={form.accountId}
                  onChange={(e) => setForm({ ...form, accountId: Number(e.target.value) })}
                >
                  {activeAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.phone} {a.display_name ? `· ${a.display_name}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              <button
                disabled={busy || !tenant || activeAccounts.length === 0 || form.link.length < 3}
                className="btn-primary"
              >
                Resolve
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={form.joinPrivate} onChange={(e) => setForm({ ...form, joinPrivate: e.target.checked })} />
              join private channel via invite link
            </label>
            {activeAccounts.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--warning)" }}>Sign in a Telegram account first (Telegram accounts tab).</p>
            ) : null}
          </form>
        )}
      </Step>

      <Step n={3} title="Bot" done={!!steps?.bot.done}>
        {steps?.bot.done ? (
          <p className="text-sm text-muted-foreground">
            @{steps.bot.username} · used for publishing and the login widget
            {botResult?.webhook_error ? <span className="block" style={{ color: "var(--warning)" }}>webhook: {botResult.webhook_error}</span> : null}
            {botResult ? <span className="block text-xs">BotFather: {botResult.setdomain_hint}</span> : null}
          </p>
        ) : (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                setBotResult(await post<BotResult>(`/api/admin/tenants/${tenant!.id}/bot`, { token: form.token }));
                setForm({ ...form, token: "" });
              });
            }}
          >
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Bot token from @BotFather</span>
                <input
                  className="input-field w-72"
                  type="password"
                  placeholder="123456:ABC-DEF…"
                  value={form.token}
                  onChange={(e) => setForm({ ...form, token: e.target.value })}
                />
              </label>
              <button disabled={busy || !steps?.channel.done} className="btn-primary">
                Connect
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              The bot must already be an admin of the channel with &quot;Post messages&quot;. Afterwards run
              <code className="mx-1 rounded bg-muted px-1">/setdomain</code>in BotFather so the login widget works.
            </p>
          </form>
        )}
      </Step>

      <Step n={4} title="DNS" done={!!steps?.domain.done}>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="text-muted-foreground">{steps?.domain.detail ?? "—"}</span>
          <button
            onClick={() => void run(() => post(`/api/admin/tenants/${tenant!.id}/verify-domain`))}
            disabled={busy || !tenant}
            className="btn-ghost py-1 text-xs"
          >
            Check DNS
          </button>
          <span className="text-xs text-muted-foreground">Point an A record at the server, then check. Certificates are issued on first visit.</span>
        </div>
      </Step>

      <Step n={5} title="Import history" done={!!steps?.backfill.done}>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <button
            onClick={() => void run(() => post(`/api/admin/tenants/${tenant!.id}/start`))}
            disabled={busy || !steps?.channel.done}
            className="btn-primary"
          >
            Start import
          </button>
          {steps?.backfill.status ? (
            <span className="text-muted-foreground">
              {steps.backfill.status} · {steps.backfill.checkpoint}
              {steps.backfill.total ? ` / ~${steps.backfill.total}` : ""} messages
            </span>
          ) : null}
        </div>
        {steps?.backfill.total ? (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${Math.min(100, Math.round(((steps.backfill.checkpoint || 0) / steps.backfill.total) * 100))}%` }}
            />
          </div>
        ) : null}
        {tenant ? (
          <p className="mt-2 text-xs text-muted-foreground">
            Blog: <a className="underline" href={`https://${tenant.domain}`} target="_blank" rel="noreferrer">{tenant.domain}</a>
          </p>
        ) : null}
      </Step>
    </div>
  );
}
