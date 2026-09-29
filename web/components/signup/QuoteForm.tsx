"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";
import { SendIcon } from "@/components/Icons";
import { compactNumber, uzs } from "@/lib/format";
import type { ChannelQuote } from "@/lib/types";

type Failure = { kind: "taken" | "invalid" | "rateLimited" | "other"; message?: string };

/**
 * osor.uz/start: anyone types a channel's username and sees what importing it costs, then
 * messages the admin. Nothing is reserved by asking; the same channel can be priced again.
 * The server answers at once with an estimate from the channel's public page when it can, and
 * refines it through Telegram in the background, so the page polls while `status` is pending.
 */
export function QuoteForm({
  initialChannel,
  initialQuote,
  contactUrl,
}: {
  initialChannel: string | null;
  initialQuote: ChannelQuote | null;
  contactUrl: string | null;
}) {
  const t = useTranslations("signup");
  const [link, setLink] = useState(initialChannel ? `@${initialChannel}` : "");
  const [quote, setQuote] = useState<ChannelQuote | null>(initialQuote);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const asked = useRef<string>("");

  const ask = useCallback(async (value: string) => {
    asked.current = value;
    setBusy(true);
    setFailure(null);
    try {
      const res = await fetch("/api/signup/quote", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ link: value }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setQuote(null);
        setFailure(
          res.status === 409
            ? { kind: "taken" }
            : res.status === 400 || res.status === 422
              ? { kind: "invalid" }
              : res.status === 429
                ? { kind: "rateLimited" }
                : { kind: "other", message: (body as { detail?: string }).detail ?? res.statusText },
        );
        return;
      }
      const q = body as ChannelQuote;
      setQuote(q);
      // Shareable and survives a reload.
      window.history.replaceState(null, "", `/start?c=${encodeURIComponent(q.username)}`);
    } catch (e) {
      setFailure({ kind: "other", message: (e as Error).message });
    } finally {
      setBusy(false);
    }
  }, []);

  // While Telegram is measuring, poll; the server gives up waiting on its own after a few minutes.
  const pending = quote?.status === "pending";
  const username = quote?.username;
  useEffect(() => {
    if (!pending || !username) return;
    const id = setInterval(async () => {
      try {
        const res = await fetch(`/api/signup/quote/${encodeURIComponent(username)}`);
        if (res.ok) setQuote((await res.json()) as ChannelQuote);
      } catch {
        /* transient; the next tick retries */
      }
    }, 4000);
    return () => clearInterval(id);
  }, [pending, username]);

  const retry = () => void ask(quote ? quote.username : asked.current || link);
  const retryButton = (
    <button className="btn-ghost mt-3" type="button" onClick={retry} disabled={busy}>
      {t("retry")}
    </button>
  );

  return (
    <section className="shell landing-section pt-10 sm:pt-14">
      <p className="eyebrow">Osor</p>
      <h1 className="landing-h2">{t("title")}</h1>
      <p className="landing-lead">{t("lead")}</p>

      <form
        className="signup-add"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(link);
        }}
      >
        <label className="stat-label" htmlFor="channel-link">
          {t("addLabel")}
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
            autoCapitalize="off"
            spellCheck={false}
          />
          <button className="btn-primary" type="submit" disabled={busy || link.trim().length < 4}>
            {t("addButton")}
          </button>
        </div>
        <p className="landing-note">{t("addHint")}</p>
      </form>

      <div className="signup-result" aria-live="polite">
        {busy && !quote ? (
          <p className="flow-calculating text-sm text-muted-foreground">
            <span className="flow-spinner" aria-hidden />
            {t("calculating")}
          </p>
        ) : failure ? (
          <div>
            <p className="text-sm" style={{ color: "var(--destructive)" }}>
              {failure.kind === "other"
                ? t("error", { message: failure.message ?? "" })
                : t(failure.kind)}
            </p>
            {failure.kind === "other" || failure.kind === "rateLimited" ? retryButton : null}
          </div>
        ) : quote ? (
          <QuoteCard quote={quote} busy={busy} retryButton={retryButton} contactUrl={contactUrl} />
        ) : null}
      </div>
    </section>
  );
}

function QuoteCard({
  quote,
  busy,
  retryButton,
  contactUrl,
}: {
  quote: ChannelQuote;
  busy: boolean;
  retryButton: React.ReactNode;
  contactUrl: string | null;
}) {
  const t = useTranslations("signup");
  const q = quote.quote;
  return (
    <div className="card landing-card signup-quote">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h2 className="text-xl font-bold">@{quote.username}</h2>
        {quote.title ? <span className="text-muted-foreground">{quote.title}</span> : null}
        {quote.participants_count ? (
          <span className="text-sm text-muted-foreground">
            {t("subscribers", { count: compactNumber(quote.participants_count) })}
          </span>
        ) : null}
      </div>

      {q ? (
        <>
          <div className="flow-quote mt-4">
            <div>
              <span className="stat-value">{compactNumber(q.posts)}</span>
              <span className="stat-label">
                {t("posts", { count: compactNumber(q.posts) })} ·{" "}
                {t(`estimatedFrom.${q.source === "telegram" ? "telegram" : "web"}`)}
              </span>
            </div>
            <div>
              <span className="stat-value">
                {uzs(q.price_uzs)}{" "}
                <small className="text-base font-semibold text-muted-foreground">
                  {t("currency")}
                </small>
              </span>
              <span className="stat-label">{t("onboardingPrice")}</span>
            </div>
          </div>
          {quote.status === "pending" ? (
            <p className="flow-calculating mt-3 text-xs text-muted-foreground">
              <span className="flow-spinner" aria-hidden />
              {t("refining")}
            </p>
          ) : null}
          <p className="landing-note">{t("onboardingPriceHint")}</p>

          <dl className="flow-summary">
            <dt>{t("summaryTitle")}</dt>
            <dd />
            <dt className="text-muted-foreground">{t("summaryImport")}</dt>
            <dd>{uzs(q.price_uzs)}</dd>
            <dt className="text-muted-foreground">{t("summaryHosting")}</dt>
            <dd>{t("hostingFree")}</dd>
            <dt>{t("summaryTotal")}</dt>
            <dd>
              {uzs(q.price_uzs)} {t("currency")}
            </dd>
          </dl>
          <p className="landing-note">{t("hostingNote")}</p>

          <h3 className="mt-6 font-bold">{t("nextTitle")}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t("nextBody")}</p>
          {contactUrl ? (
            <a href={contactUrl} target="_blank" rel="noreferrer" className="btn-primary mt-3">
              <SendIcon size={16} />
              {t("contactAdmin")}
            </a>
          ) : null}
        </>
      ) : quote.status === "pending" ? (
        <p className="flow-calculating mt-4 text-sm text-muted-foreground">
          <span className="flow-spinner" aria-hidden />
          {t("calculating")}
        </p>
      ) : (
        <div className="mt-4">
          <p className="text-sm" style={{ color: "var(--warning)" }}>
            {t("failed")}
          </p>
          {busy ? (
            <p className="flow-calculating mt-3 text-sm text-muted-foreground">
              <span className="flow-spinner" aria-hidden />
              {t("calculating")}
            </p>
          ) : (
            retryButton
          )}
        </div>
      )}
    </div>
  );
}
