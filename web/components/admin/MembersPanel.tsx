"use client";

import { useState } from "react";
import { call, del, post } from "@/lib/client";
import type { MemberOut } from "@/lib/types";

/**
 * Who can enter this channel's studio. An invited person signs in with Telegram like anyone
 * else, but the channel is not asked whether they administer it — which is what makes a
 * channel without a bot of its own usable at all.
 */
export function MembersPanel({ tenantId, initial }: { tenantId: number; initial: MemberOut[] }) {
  const [members, setMembers] = useState(initial);
  const [form, setForm] = useState({ id: "", name: "", role: "owner" as "owner" | "editor" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/admin/tenants/${tenantId}/members`;

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setMembers(await call<MemberOut[]>(base));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card-surface p-4">
      <h2 className="text-sm font-medium">Studio access</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Channel admins get in on their own once a bot is connected. Anyone listed here gets in regardless —
        add the blogger&apos;s Telegram id to onboard without a bot.
      </p>

      {members.length > 0 ? (
        <ul className="mt-3 divide-y text-sm">
          {members.map((m) => (
            <li key={m.tg_user_id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="min-w-0 flex-1 truncate">
                {m.name}
                {m.username ? <span className="text-muted-foreground"> @{m.username}</span> : null}
              </span>
              <span className="chip">{m.role}</span>
              <span className="text-xs text-muted-foreground">
                {m.invited ? "invited" : "verified admin"} · id {m.tg_user_id}
                {m.last_login_at ? "" : " · never signed in"}
              </span>
              <button
                disabled={busy}
                onClick={() => void run(() => del(`${base}/${m.tg_user_id}`))}
                className="link-quiet text-xs"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">Nobody yet.</p>
      )}

      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await post(base, { tg_user_id: Number(form.id), role: form.role, name: form.name || null });
            setForm({ id: "", name: "", role: "owner" });
          });
        }}
      >
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">Telegram user id</span>
          <input
            className="input-field w-40"
            inputMode="numeric"
            placeholder="123456789"
            value={form.id}
            onChange={(e) => setForm({ ...form, id: e.target.value.replace(/\D/g, "") })}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">Name (optional)</span>
          <input className="input-field w-40" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs text-muted-foreground">Role</span>
          <select
            className="input-field w-auto"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as "owner" | "editor" })}
          >
            <option value="owner">owner</option>
            <option value="editor">editor</option>
          </select>
        </label>
        <button disabled={busy || form.id.length < 3} className="btn-ghost">
          Invite
        </button>
        <span className="basis-full text-xs text-muted-foreground">
          They can find their id by messaging @userinfobot on Telegram.
        </span>
      </form>
      {error ? (
        <p className="mt-2 text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
