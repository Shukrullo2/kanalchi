"use client";

import { useEffect, useState } from "react";
import { State } from "@/components/admin/StatusDot";
import { call, del, post } from "@/lib/client";
import type { TgAccount } from "@/lib/types";

export function AccountsManager({ initial }: { initial: TgAccount[] }) {
  const [accounts, setAccounts] = useState(initial);
  const [phone, setPhone] = useState("");
  const [secret, setSecret] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const pending = accounts.some((a) => a.status.startsWith("pending"));
  useEffect(() => {
    if (!pending) return;
    const id = setInterval(async () => setAccounts(await call<TgAccount[]>("/api/admin/accounts")), 2000);
    return () => clearInterval(id);
  }, [pending]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setAccounts(await call<TgAccount[]>("/api/admin/accounts"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await post("/api/admin/accounts", { phone });
            setPhone("");
          });
        }}
      >
        <label className="text-sm">
          <span className="mb-1 block text-muted-foreground">Phone (international format)</span>
          <input
            className="input-field w-56"
            placeholder="+998901234567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <button disabled={busy || phone.length < 6} className="btn-primary">
          Send code
        </button>
        <p className="w-full text-xs text-muted-foreground">
          Use a dedicated account, not a personal one. Telegram sends the code to that account&apos;s app.
        </p>
      </form>

      {error ? <p className="rounded-md border px-3 py-2 text-sm" style={{ color: "var(--destructive)", borderColor: "var(--destructive)" }}>{error}</p> : null}

      {accounts.length > 0 ? (
      <ul className="rows mt-6 border-t">
        {accounts.map((a) => (
          <li key={a.id} className="row text-sm" style={{ "--state-w": "11rem" } as React.CSSProperties}>
            <span className="row-margin">
              <State status={a.status} />
              {a.last_seen_at ? <span suppressHydrationWarning>{seen(a.last_seen_at)}</span> : null}
            </span>
            <div className="row-body">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-medium">{a.phone}</span>
              {a.display_name ? <span className="text-muted-foreground">{a.display_name}</span> : null}
              <button
                onClick={() => void run(() => del(`/api/admin/accounts/${a.id}`))}
                className="link-quiet ml-auto text-xs"
              >
                Disable
              </button>
            </div>
            {typeof a.health?.last_error === "string" && a.health.last_error ? (
              <p className="mt-1 text-xs" style={{ color: "var(--destructive)" }}>{a.health.last_error as string}</p>
            ) : null}
            {a.status === "pending_code" || a.status === "pending_password" ? (
              <form
                className="mt-2 flex flex-wrap items-center gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const kind = a.status === "pending_code" ? "code" : "password";
                  void run(async () => {
                    await post(`/api/admin/accounts/${a.id}/${kind}`, { value: secret[a.id] ?? "" });
                    setSecret((s) => ({ ...s, [a.id]: "" }));
                  });
                }}
              >
                <input
                  className="input-field w-40"
                  type={a.status === "pending_password" ? "password" : "text"}
                  placeholder={a.status === "pending_code" ? "12345" : "2FA password"}
                  value={secret[a.id] ?? ""}
                  onChange={(e) => setSecret((s) => ({ ...s, [a.id]: e.target.value }))}
                />
                <button className="btn-primary py-1 text-xs">Confirm</button>
                {a.status === "pending_code" ? (
                  <button
                    type="button"
                    onClick={() => void run(() => post(`/api/admin/accounts/${a.id}/resend`))}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    Send another code
                  </button>
                ) : null}
                <span className="text-xs text-muted-foreground">
                  The Telegram worker has to be running for this to go through.
                </span>
              </form>
            ) : null}
            </div>
          </li>
        ))}
      </ul>
      ) : (
        <p className="mt-6 border-t py-12 text-center text-sm text-muted-foreground">
          No accounts yet. Add the phone number of a spare Telegram account above — it is what reads the
          channel history.
        </p>
      )}
    </div>
  );
}

/** Last seen, in UTC, written identically on the server and in the browser. */
function seen(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `seen ${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}
