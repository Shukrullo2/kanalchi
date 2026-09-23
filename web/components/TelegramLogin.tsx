"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

type TgUser = { id: number; first_name?: string; last_name?: string; username?: string; photo_url?: string; auth_date: number; hash: string };

declare global {
  interface Window {
    onTelegramAuth?: (user: TgUser) => void;
  }
}

/**
 * Telegram Login Widget → POST /api/auth/telegram. In dev without a bot, shows a
 * dev-login form instead — that form stays in English on purpose: it never ships.
 */
export function TelegramLogin({
  botUsername,
  dev,
  notConfigured,
}: {
  botUsername: string | null;
  dev: boolean;
  /** Shown to a real blogger when the host has no login bot. */
  notConfigured: string;
}) {
  const router = useRouter();
  const holder = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [devId, setDevId] = useState("1");

  useEffect(() => {
    if (!botUsername || !holder.current) return;
    window.onTelegramAuth = async (user) => {
      const res = await fetch("/api/auth/telegram", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(user),
      });
      if (!res.ok) {
        setError((await res.json().catch(() => ({}))).detail ?? "login failed");
        return;
      }
      router.refresh();
    };
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", botUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-request-access", "write");
    script.setAttribute("data-onauth", "onTelegramAuth(user)");
    holder.current.replaceChildren(script);
    return () => {
      delete window.onTelegramAuth;
    };
  }, [botUsername, router]);

  async function devLogin(e: React.FormEvent) {
    e.preventDefault();
    const res = await fetch("/api/auth/dev-login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tg_user_id: Number(devId), name: `Dev ${devId}` }),
    });
    if (!res.ok) {
      setError((await res.json().catch(() => ({}))).detail ?? "dev login failed");
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col items-center gap-3">
      {botUsername ? <div ref={holder} /> : null}
      {dev ? (
        <form onSubmit={devLogin} className="flex items-center gap-2 rounded-lg border border-dashed p-3 text-sm">
          <span className="text-muted-foreground">dev login · tg id</span>
          <input
            className="input-field w-24"
            value={devId}
            onChange={(e) => setDevId(e.target.value)}
            inputMode="numeric"
          />
          <button className="btn-primary py-1.5" type="submit">
            Sign in
          </button>
        </form>
      ) : null}
      {!botUsername && !dev ? <p className="text-sm text-muted-foreground">{notConfigured}</p> : null}
      {error ? <p className="text-sm" style={{ color: "var(--destructive)" }}>{error}</p> : null}
    </div>
  );
}
