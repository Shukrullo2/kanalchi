"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { patch, post } from "@/lib/client";
import type { StudioSettings } from "@/lib/types";

export function SettingsPanel({ initial }: { initial: StudioSettings }) {
  const router = useRouter();
  const [settings, setSettings] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(label);
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const voice = settings.voice_profile as Record<string, unknown> | null;

  return (
    <div className="space-y-4">
      {error ? (
        <p className="text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}

      <section className="card-surface space-y-3 p-4">
        <h2 className="text-sm font-medium">Reader assistant</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.chat_enabled}
            onChange={(e) => {
              const chat_enabled = e.target.checked;
              setSettings({ ...settings, chat_enabled });
              void run(chat_enabled ? "Assistant on." : "Assistant off.", () =>
                patch("/api/studio/settings", { chat_enabled }),
              );
            }}
          />
          Let readers ask questions about your channel
        </label>
        <p className="text-xs text-muted-foreground">
          Answers only ever come from your posts, and every claim links back to the original.
        </p>
      </section>

      <section className="card-surface space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium">Your writing voice</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Built from your own posts, so AI drafts sound like you rather than like an assistant.
            </p>
          </div>
          <button
            onClick={() => void run("Rebuilding your voice profile…", () => post("/api/studio/voice/rebuild", {}))}
            disabled={busy}
            className="btn-ghost shrink-0 py-1 text-xs"
          >
            {voice ? "Rebuild" : "Build"}
          </button>
        </div>
        {voice ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            {["tone", "formality", "language_mix", "emoji_usage"].map((key) =>
              voice[key] ? (
                <div key={key} className="rounded-lg bg-surface-2 p-2.5">
                  <dt className="text-[0.65rem] uppercase tracking-wider text-muted-foreground">
                    {key.replace(/_/g, " ")}
                  </dt>
                  <dd className="mt-0.5 text-xs">{String(voice[key])}</dd>
                </div>
              ) : null,
            )}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">Not built yet.</p>
        )}
      </section>

      <section className="card-surface space-y-2 p-4 text-sm">
        <h2 className="font-medium">Publishing</h2>
        <p className="text-xs text-muted-foreground">
          {settings.bot_username ? (
            <>
              Posts are sent by <span className="font-medium">@{settings.bot_username}</span>
              {settings.webhook_ready ? ", which is connected." : ", but its webhook is not set up yet."}
            </>
          ) : (
            "No bot is connected yet. Ask the platform admin to add one."
          )}
        </p>
        <p className="text-xs text-muted-foreground">Languages: {settings.locales.join(", ")}</p>
      </section>
    </div>
  );
}
