"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { call, del, patch, post } from "@/lib/client";
import type { MemberOut, StudioSettings } from "@/lib/types";

export function SettingsPanel({
  initial,
  members: initialMembers,
  meId,
}: {
  initial: StudioSettings;
  members: MemberOut[];
  /** The signed-in member's Telegram id, so their own row is marked and cannot be removed. */
  meId: number | null;
}) {
  const t = useTranslations("studio.settings");
  const router = useRouter();
  const [settings, setSettings] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(label: string, fn: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setNotice(label);
      router.refresh();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const voice = settings.voice_profile as Record<string, unknown> | null;
  const [members, setMembers] = useState(initialMembers);
  const [invite, setInvite] = useState({ id: "", name: "", role: "editor" as "owner" | "editor" });
  const owner = settings.role === "owner";

  async function team(label: string, fn: () => Promise<unknown>) {
    if (await run(label, fn)) setMembers(await call<MemberOut[]>("/api/studio/members"));
  }

  return (
    <div className="divide-y">
      {settings.paused ? (
        <p className="border-l-2 py-1 pl-3 text-sm" style={{ borderColor: "var(--warning)" }}>
          {t("paused")}
        </p>
      ) : null}
      {error ? (
        <p className="text-sm" style={{ color: "var(--destructive)" }}>
          {error}
        </p>
      ) : null}
      {notice ? <p className="text-sm text-muted-foreground">{notice}</p> : null}

      <section className="space-y-3 py-5">
        <h2 className="text-sm font-medium">{t("readerAssistant")}</h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.chat_enabled}
            onChange={(e) => {
              const chat_enabled = e.target.checked;
              setSettings({ ...settings, chat_enabled });
              void run(chat_enabled ? t("assistantOn") : t("assistantOff"), () =>
                patch("/api/studio/settings", { chat_enabled }),
              ).then((ok) => {
                // The box flipped before the server answered; flip it back if the save failed.
                if (!ok) setSettings((s) => ({ ...s, chat_enabled: !chat_enabled }));
              });
            }}
          />
          {t("letReaders")}
        </label>
        <p className="text-xs text-muted-foreground">
          {t("answersFrom")}
        </p>
      </section>

      <section className="space-y-3 py-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-medium">{t("voice")}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t("voiceBody")}
            </p>
          </div>
          <button
            onClick={() => void run(t("rebuilding"), () => post("/api/studio/voice/rebuild", {}))}
            disabled={busy}
            className="btn-ghost shrink-0 py-1 text-xs"
          >
            {voice ? t("rebuild") : t("build")}
          </button>
        </div>
        {voice ? (
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            {["tone", "formality", "language_mix", "emoji_usage"].map((key) =>
              voice[key] ? (
                <div key={key} className="rounded-lg bg-surface-2 p-2.5">
                  <dt className="text-xs text-muted-foreground">{t(key as "tone")}</dt>
                  <dd className="mt-0.5 text-xs">{String(voice[key])}</dd>
                </div>
              ) : null,
            )}
          </dl>
        ) : (
          <p className="text-xs text-muted-foreground">{t("notBuilt")}</p>
        )}
      </section>

      <section className="space-y-2 py-5 text-sm">
        <h2 className="font-medium">{t("publishing")}</h2>
        <p className="text-xs text-muted-foreground">
          {settings.bot_username
            ? settings.webhook_ready
              ? t("botConnected", { bot: settings.bot_username })
              : t("botNoWebhook", { bot: settings.bot_username })
            : t("noBot")}
        </p>
        {settings.bot_username ? (
          <p className="text-xs" style={settings.notifications_linked ? undefined : { color: "var(--warning)" }}>
            {settings.notifications_linked
              ? t("notificationsOk")
              : t.rich("startBot", {
                  bot: settings.bot_username,
                  a: (chunks) => (
                    <a className="underline" href={`https://t.me/${settings.bot_username}?start=studio`} target="_blank" rel="noreferrer">
                      {chunks}
                    </a>
                  ),
                })}
          </p>
        ) : null}
        <p className="text-xs text-muted-foreground">{t("languages", { list: settings.locales.join(", ") })}</p>
      </section>

      <section className="space-y-3 py-5 text-sm">
        <div>
          <h2 className="font-medium">{t("team")}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">{t("teamBody")}</p>
        </div>
        <ul className="divide-y">
          {members.map((m) => (
            <li key={m.tg_user_id} className="flex flex-wrap items-center gap-3 py-2">
              <span className="min-w-0 flex-1 truncate">
                {m.name}
                {m.username ? <span className="text-muted-foreground"> @{m.username}</span> : null}
                {m.tg_user_id === meId ? <span className="text-muted-foreground"> · {t("you")}</span> : null}
              </span>
              <span className="chip">{m.role === "owner" ? t("roleOwner") : t("roleEditor")}</span>
              {m.invited ? <span className="text-xs text-muted-foreground">{t("invited")}</span> : null}
              {owner && m.tg_user_id !== meId ? (
                <button
                  disabled={busy}
                  onClick={() => void team(t("memberRemoved"), () => del(`/api/studio/members/${m.tg_user_id}`))}
                  className="link-quiet text-xs"
                >
                  {t("remove")}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
        {owner ? (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void team(t("memberAdded"), async () => {
                await post("/api/studio/members", {
                  tg_user_id: Number(invite.id),
                  role: invite.role,
                  name: invite.name || null,
                });
                setInvite({ id: "", name: "", role: "editor" });
              });
            }}
          >
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted-foreground">{t("memberId")}</span>
              <input
                className="input-field w-40"
                inputMode="numeric"
                value={invite.id}
                onChange={(e) => setInvite({ ...invite, id: e.target.value.replace(/\D/g, "") })}
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted-foreground">{t("memberName")}</span>
              <input className="input-field w-40" value={invite.name} onChange={(e) => setInvite({ ...invite, name: e.target.value })} />
            </label>
            <select
              className="input-field w-auto"
              value={invite.role}
              onChange={(e) => setInvite({ ...invite, role: e.target.value as "owner" | "editor" })}
            >
              <option value="editor">{t("roleEditor")}</option>
              <option value="owner">{t("roleOwner")}</option>
            </select>
            <button disabled={busy || invite.id.length < 3} className="btn-ghost">
              {t("addMember")}
            </button>
            <span className="basis-full text-xs text-muted-foreground">{t("memberIdHint")}</span>
          </form>
        ) : null}
      </section>
    </div>
  );
}
