"use client";

import { useEffect, useState } from "react";
import { call, del, post } from "@/lib/client";
import type { TgAccount } from "@/lib/types";

const BADGE: Record<string, string> = {
  active: "bg-green-100 text-green-800",
  pending_code: "bg-amber-100 text-amber-800",
  pending_password: "bg-amber-100 text-amber-800",
  flood_wait: "bg-orange-100 text-orange-800",
  dead: "bg-red-100 text-red-800",
  disabled: "bg-neutral-200 text-neutral-700",
};

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
            className="w-56 rounded border bg-transparent px-2 py-1"
            placeholder="+998901234567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>
        <button disabled={busy || phone.length < 6} className="rounded bg-foreground px-3 py-1.5 text-sm text-background disabled:opacity-50">
          Send code
        </button>
        <p className="w-full text-xs text-muted-foreground">
          Use a dedicated account, not a personal one. Telegram sends the code to that account&apos;s app.
        </p>
      </form>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <div className="space-y-3">
        {accounts.map((a) => (
          <div key={a.id} className="rounded-lg border p-3 text-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-medium">{a.phone}</span>
              <span className={`rounded px-1.5 py-0.5 text-xs ${BADGE[a.status] ?? "bg-neutral-100"}`}>{a.status}</span>
              {a.display_name ? <span className="text-muted-foreground">{a.display_name}</span> : null}
              {a.last_seen_at ? (
                <span className="text-xs text-muted-foreground">seen {new Date(a.last_seen_at).toLocaleString()}</span>
              ) : null}
              <button
                onClick={() => void run(() => del(`/api/admin/accounts/${a.id}`))}
                className="ml-auto text-xs text-muted-foreground hover:text-red-600"
              >
                disable
              </button>
            </div>
            {typeof a.health?.last_error === "string" && a.health.last_error ? (
              <p className="mt-1 text-xs text-red-600">{a.health.last_error as string}</p>
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
                  className="w-40 rounded border bg-transparent px-2 py-1"
                  type={a.status === "pending_password" ? "password" : "text"}
                  placeholder={a.status === "pending_code" ? "12345" : "2FA password"}
                  value={secret[a.id] ?? ""}
                  onChange={(e) => setSecret((s) => ({ ...s, [a.id]: e.target.value }))}
                />
                <button className="rounded bg-foreground px-3 py-1 text-xs text-background">submit</button>
                {a.status === "pending_code" ? (
                  <button
                    type="button"
                    onClick={() => void run(() => post(`/api/admin/accounts/${a.id}/resend`))}
                    className="text-xs text-muted-foreground hover:text-foreground"
                  >
                    resend
                  </button>
                ) : null}
                <span className="text-xs text-muted-foreground">
                  worker-telegram must be running for the login to complete
                </span>
              </form>
            ) : null}
          </div>
        ))}
        {accounts.length === 0 ? <p className="text-sm text-muted-foreground">No accounts yet.</p> : null}
      </div>
    </div>
  );
}
