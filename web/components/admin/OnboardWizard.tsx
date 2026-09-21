"use client";

import { useEffect, useState } from "react";
import { call, post } from "@/lib/client";
import type { AdminTenant, Checklist, TgAccount } from "@/lib/types";

type BotResult = { bot_username: string; webhook_set: boolean; webhook_error: string | null; setdomain_hint: string };

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border p-4">
      <h2 className="mb-2 flex items-center gap-2 font-medium">
        <span className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${done ? "bg-green-600 text-white" : "bg-muted"}`}>
          {done ? "✓" : n}
        </span>
        {title}
      </h2>
      {children}
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
    <div className="max-w-2xl space-y-4">
      {error ? <p className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-700">{error}</p> : null}

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
                className="w-56 rounded border bg-transparent px-2 py-1"
                placeholder="blog.example.uz"
                value={form.domain}
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-muted-foreground">Title (optional)</span>
              <input
                className="w-48 rounded border bg-transparent px-2 py-1"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <button disabled={busy || form.domain.length < 3} className="rounded bg-foreground px-3 py-1.5 text-sm text-background disabled:opacity-50">
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
                  className="w-64 rounded border bg-transparent px-2 py-1"
                  placeholder="https://t.me/mychannel"
                  value={form.link}
                  onChange={(e) => setForm({ ...form, link: e.target.value })}
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Telegram account</span>
                <select
                  className="rounded border bg-transparent px-2 py-1"
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
                className="rounded bg-foreground px-3 py-1.5 text-sm text-background disabled:opacity-50"
              >
                Resolve
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={form.joinPrivate} onChange={(e) => setForm({ ...form, joinPrivate: e.target.checked })} />
              join private channel via invite link
            </label>
            {activeAccounts.length === 0 ? (
              <p className="text-xs text-amber-700">Sign in a Telegram account first (Telegram accounts tab).</p>
            ) : null}
          </form>
        )}
      </Step>

      <Step n={3} title="Bot" done={!!steps?.bot.done}>
        {steps?.bot.done ? (
          <p className="text-sm text-muted-foreground">
            @{steps.bot.username} · used for publishing and the login widget
            {botResult?.webhook_error ? <span className="block text-amber-700">webhook: {botResult.webhook_error}</span> : null}
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
                  className="w-72 rounded border bg-transparent px-2 py-1"
                  type="password"
                  placeholder="123456:ABC-DEF…"
                  value={form.token}
                  onChange={(e) => setForm({ ...form, token: e.target.value })}
                />
              </label>
              <button disabled={busy || !steps?.channel.done} className="rounded bg-foreground px-3 py-1.5 text-sm text-background disabled:opacity-50">
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
            className="rounded border px-3 py-1 text-xs disabled:opacity-50"
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
            className="rounded bg-foreground px-3 py-1.5 text-background disabled:opacity-50"
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
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-muted">
            <div
              className="h-full bg-foreground transition-all"
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
