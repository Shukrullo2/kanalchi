"use client";

import Link from "@/components/AppLink";
import { useEffect, useState } from "react";
import { PipelineMonitor } from "@/components/admin/PipelineMonitor";
import { call, patch, post } from "@/lib/client";
import type { AdminTenant, Checklist, TgAccount } from "@/lib/types";

type BotResult = { bot_username: string; webhook_set: boolean; webhook_error: string | null; setdomain_hint: string };

/**
 * Connecting a channel is a sequence, so the numbers are information and sit in the
 * margin. Only the first two steps are required: a channel is live under the platform
 * domain as soon as its history is in. A domain and a bot of its own can come later.
 */
function Step({
  n,
  title,
  done,
  optional,
  children,
}: {
  n: number;
  title: string;
  done: boolean;
  optional?: boolean;
  children: React.ReactNode;
}) {
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
          {optional ? <span className="ml-2 text-xs font-normal text-muted-foreground">optional</span> : null}
          <span className="sr-only">{done ? " — done" : " — not done yet"}</span>
        </h2>
        {children}
      </div>
    </section>
  );
}

export function OnboardWizard({
  accounts,
  resume,
}: {
  accounts: TgAccount[];
  /** Continue with a channel created earlier (`?tenant=<id>`), state being otherwise in this tab only. */
  resume?: { tenant: AdminTenant; checklist: Checklist } | null;
}) {
  // Only a signed-in account can read a channel, and it is the only kind the select offers,
  // so the default has to be one of those too.
  const activeAccounts = accounts.filter((a) => a.status === "active");
  const [tenant, setTenant] = useState<AdminTenant | null>(resume?.tenant ?? null);
  const [checklist, setChecklist] = useState<Checklist | null>(resume?.checklist ?? null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    link: "",
    accountId: activeAccounts[0]?.id ?? 0,
    joinPrivate: false,
    title: "",
    ownerId: "",
    ownerName: "",
    domain: "",
    token: "",
  });
  const [botResult, setBotResult] = useState<BotResult | null>(null);
  const [dns, setDns] = useState<string | null>(null);

  async function refresh(id: number) {
    try {
      const [c, t] = await Promise.all([
        call<Checklist>(`/api/admin/tenants/${id}/checklist`),
        call<AdminTenant>(`/api/admin/tenants/${id}`),
      ]);
      setChecklist(c);
      setTenant(t);
    } catch {
      // The monitor below says "reconnecting"; the steps keep their last known state.
    }
  }

  const steps = checklist?.steps;
  const channelDone = !!steps?.channel.done;
  useEffect(() => {
    if (!tenant) return;
    // Quick while the resolve job is running; slow afterwards, when only clicks change anything.
    const id = setInterval(() => void refresh(tenant.id), channelDone ? 15_000 : 3_000);
    return () => clearInterval(id);
  }, [tenant, channelDone]);

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

  const resolveFailed = checklist?.last_error?.type === "resolve" ? checklist.last_error.error : null;

  return (
    <div className="rows max-w-3xl">
      {error ? (
        <p className="border-l-2 py-1 pl-3 text-sm" style={{ color: "var(--destructive)", borderColor: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}

      <Step n={1} title="Channel" done={channelDone}>
        {channelDone && steps ? (
          <p className="text-sm text-muted-foreground">
            {steps.channel.title} {steps.channel.username ? `(@${steps.channel.username})` : "(private)"} ·{" "}
            {steps.channel.total ?? "?"} posts
            {steps.channel.noforwards ? " · protected content: media stays on Telegram" : ""}
            {tenant ? ` · tenant #${tenant.id}` : ""}
          </p>
        ) : (
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                const t =
                  tenant ??
                  (await post<AdminTenant>("/api/admin/tenants", {
                    title: form.title || "",
                    owner_tg_id: form.ownerId ? Number(form.ownerId) : null,
                    owner_name: form.ownerName || null,
                  }));
                setTenant(t);
                await post(`/api/admin/tenants/${t.id}/channel`, {
                  link: form.link,
                  account_id: Number(form.accountId),
                  allow_join_private: form.joinPrivate,
                });
                await refresh(t.id);
              });
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
              <button disabled={busy || activeAccounts.length === 0 || form.link.length < 3} className="btn-primary">
                {tenant ? "Resolve again" : "Connect"}
              </button>
            </div>
            <div className="flex flex-wrap items-end gap-2">
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Blogger&apos;s Telegram id (optional)</span>
                <input
                  className="input-field w-40"
                  inputMode="numeric"
                  placeholder="123456789"
                  value={form.ownerId}
                  onChange={(e) => setForm({ ...form, ownerId: e.target.value.replace(/\D/g, "") })}
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Their name</span>
                <input
                  className="input-field w-40"
                  value={form.ownerName}
                  onChange={(e) => setForm({ ...form, ownerName: e.target.value })}
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Blog title (optional)</span>
                <input className="input-field w-48" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
              </label>
            </div>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input type="checkbox" checked={form.joinPrivate} onChange={(e) => setForm({ ...form, joinPrivate: e.target.checked })} />
              join private channel via invite link
            </label>
            <p className="text-xs text-muted-foreground">
              With their Telegram id the blogger can sign in to the studio straight away, bot or no bot. They can
              find it by messaging @userinfobot.
            </p>
            {activeAccounts.length === 0 ? (
              <p className="text-xs" style={{ color: "var(--warning)" }}>
                Sign in a Telegram account first (Telegram accounts tab).
              </p>
            ) : null}
            {tenant && !resolveFailed ? (
              <p className="text-xs text-muted-foreground">
                Resolving the channel… this runs in worker-telegram and takes a few seconds.
              </p>
            ) : null}
            {resolveFailed ? (
              <p className="text-xs" style={{ color: "var(--destructive)" }}>
                Resolve failed: {resolveFailed}. Fix the link or account and try again.
              </p>
            ) : null}
          </form>
        )}
      </Step>

      <Step n={2} title="Import and index" done={checklist?.pipeline?.stage === "done"}>
        {tenant && channelDone ? (
          <PipelineMonitor tenantId={tenant.id} initial={checklist} />
        ) : (
          <p className="text-sm text-muted-foreground">Waits for the channel. The cost is estimated before anything starts.</p>
        )}
      </Step>

      <Step n={3} title="Domain" done={!!tenant && !tenant.auto_domain && !!steps?.domain.done} optional>
        {tenant ? (
          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">
              Live at{" "}
              <a className="underline" href={`https://${tenant.domain}`} target="_blank" rel="noreferrer">
                {tenant.domain}
              </a>
              {tenant.auto_domain ? " under the platform domain. A domain of its own is optional." : ""}
            </p>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void run(() => patch(`/api/admin/tenants/${tenant.id}`, { domain: form.domain.trim() }));
              }}
            >
              <label className="text-sm">
                <span className="mb-1 block text-muted-foreground">Custom domain</span>
                <input
                  className="input-field w-64"
                  placeholder="blog.example.uz"
                  value={form.domain}
                  onChange={(e) => setForm({ ...form, domain: e.target.value })}
                />
              </label>
              <button disabled={busy || form.domain.trim().length < 3} className="btn-ghost">
                Set domain
              </button>
              {!tenant.auto_domain ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      const out = await post<{ ok: boolean; detail: string }>(`/api/admin/tenants/${tenant.id}/verify-domain`);
                      setDns(out.detail);
                    })
                  }
                  className="btn-ghost"
                >
                  Check DNS
                </button>
              ) : null}
            </form>
            {!tenant.auto_domain ? (
              <p className="text-xs text-muted-foreground">
                {dns ?? steps?.domain.detail ?? "Point an A record at the server, then check. Certificates are issued on first visit."}
              </p>
            ) : null}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Waits for the channel.</p>
        )}
      </Step>

      <Step n={4} title="Bot" done={!!steps?.bot.done} optional>
        {steps?.bot.done ? (
          <p className="text-sm text-muted-foreground">
            @{steps.bot.username} · used for publishing and the login widget
            {botResult?.webhook_error ? (
              <span className="block" style={{ color: "var(--warning)" }}>
                webhook: {botResult.webhook_error}
              </span>
            ) : null}
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
              <button disabled={busy || !channelDone || form.token.length < 20} className="btn-primary">
                Connect
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Without a bot the blog and studio still work: bloggers sign in through the platform bot, but cannot
              publish from the studio or get notifications. With one, it must be an admin of the channel with
              &quot;Post messages&quot;; afterwards run <code className="mx-1 rounded bg-muted px-1">/setdomain</code> in
              BotFather so the login widget works on the channel&apos;s domain.
            </p>
          </form>
        )}
      </Step>

      {tenant ? (
        <p className="pt-4 text-sm text-muted-foreground">
          Everything here continues on the{" "}
          <Link href={`/tenants/${tenant.id}`} className="underline">
            channel page
          </Link>
          .
        </p>
      ) : null}
    </div>
  );
}
