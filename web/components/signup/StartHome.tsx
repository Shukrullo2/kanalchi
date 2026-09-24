"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { ArrowRightIcon } from "@/components/Icons";
import { post } from "@/lib/client";
import { compactNumber } from "@/lib/format";
import type { SignupChannel } from "@/lib/types";

/** A signed-in blogger's channels, and the form that adds one. */
export function StartHome({
  channels,
  name,
}: {
  channels: SignupChannel[];
  name: string;
}) {
  const t = useTranslations("signup");
  const router = useRouter();
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const ch = await post<SignupChannel>("/api/signup/channels", { link });
      router.push(`/start/${ch.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <section className="shell landing-section pt-10 sm:pt-14">
      <p className="eyebrow">{t("title")}</p>
      <h1 className="landing-h2">{t("hello", { name })}</h1>

      <form onSubmit={add} className="signup-add">
        <label className="stat-label" htmlFor="channel-link">
          {t("addTitle")}
        </label>
        <div className="signup-add-row">
          <input
            id="channel-link"
            className="input-field"
            placeholder={t("addPlaceholder")}
            value={link}
            onChange={(e) => setLink(e.target.value)}
            required
            autoComplete="off"
          />
          <button
            className="btn-primary"
            type="submit"
            disabled={busy || link.trim().length < 4}
          >
            {t("addButton")}
          </button>
        </div>
        <p className="landing-note">{t("addHint")}</p>
        {error ? (
          <p className="text-sm" style={{ color: "var(--destructive)" }}>
            {t("error", { message: error })}
          </p>
        ) : null}
      </form>

      <h2 className="mt-10 text-lg font-bold">{t("myChannels")}</h2>
      {channels.length === 0 ? (
        <p className="landing-note">{t("noChannels")}</p>
      ) : (
        <ul className="mt-3 grid gap-3 sm:grid-cols-2">
          {channels.map((c) => (
            <li key={c.id}>
              <a
                href={`/start/${c.id}`}
                className="card landing-card signup-channel"
              >
                <span className="flex items-baseline justify-between gap-3">
                  <span className="truncate font-bold">
                    {c.channel.username ? `@${c.channel.username}` : c.title}
                  </span>
                  <span className="chip">
                    {t(`status.${c.status}` as never)}
                  </span>
                </span>
                <span className="text-sm text-muted-foreground">
                  {c.domain}
                </span>
                <span className="flex flex-wrap gap-x-4 text-xs text-muted-foreground">
                  {c.channel.posts_estimate ? (
                    <span>
                      {t("posts", {
                        count: compactNumber(c.channel.posts_estimate),
                      })}
                    </span>
                  ) : null}
                  {c.channel.participants_count ? (
                    <span>
                      {t("subscribers", {
                        count: compactNumber(c.channel.participants_count),
                      })}
                    </span>
                  ) : null}
                  {c.plan ? <span>{t(`plans.${c.plan}.name`)}</span> : null}
                </span>
                <span className="mt-1 inline-flex items-center gap-1 text-sm font-semibold text-primary">
                  {t("open")} <ArrowRightIcon size={14} />
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
