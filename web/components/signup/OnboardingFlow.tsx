"use client";

import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeftIcon, ExternalIcon, SendIcon } from "@/components/Icons";
import { PlanCards } from "@/components/signup/PlanCards";
import { call, patch, post } from "@/lib/client";
import { compactNumber, fullDate, uzs } from "@/lib/format";
import type { Plan, PlanId, SignupChannel } from "@/lib/types";

type StepKey = "estimate" | "verify" | "plan" | "payment" | "import" | "live";

/**
 * One channel's road from "added" to "live", as a vertical checklist. Every step is derived
 * from the channel record, so the page just polls and re-renders; the admin's actions
 * (payment marked, import started) show up here on their own.
 */
export function OnboardingFlow({
  initial,
  plans,
  botUsername,
  contactUrl,
}: {
  initial: SignupChannel;
  plans: Plan[];
  botUsername: string | null;
  contactUrl: string | null;
}) {
  const t = useTranslations("signup");
  const locale = useLocale();
  const router = useRouter();
  const [ch, setCh] = useState(initial);
  const [posts, setPosts] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<boolean | null>(null);
  // Flips four minutes after the channel was added, in case the preview job never answers.
  const [previewStale, setPreviewStale] = useState(false);
  useEffect(() => {
    const left =
      4 * 60 * 1000 - (Date.now() - new Date(initial.created_at).getTime());
    const id = setTimeout(() => setPreviewStale(true), Math.max(0, left));
    return () => clearTimeout(id);
  }, [initial.created_at]);

  const refresh = useCallback(async () => {
    try {
      setCh(await call<SignupChannel>(`/api/signup/channels/${initial.id}`));
    } catch {
      /* transient; the next tick retries */
    }
  }, [initial.id]);

  useEffect(() => {
    const id = setInterval(() => void refresh(), 6000);
    return () => clearInterval(id);
  }, [refresh]);

  async function run(label: string, fn: () => Promise<SignupChannel | void>) {
    setBusy(label);
    setError(null);
    try {
      const next = await fn();
      if (next) setCh(next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const requested = Boolean(ch.requested_at);
  const paid = Boolean(ch.onboarding_paid_at);
  const imported =
    ch.progress.backfill_status === "done" ||
    ch.status === "indexing" ||
    ch.status === "active";
  const done: Record<StepKey, boolean> = {
    estimate: ch.quote !== null,
    verify: ch.verified || ch.verify_skipped,
    plan: ch.plan !== null && requested,
    payment: paid,
    import: imported,
    live: ch.status === "active",
  };
  const order: StepKey[] = [
    "estimate",
    "verify",
    "plan",
    "payment",
    "import",
    "live",
  ];
  // Verification is optional, so a later step can be done while an earlier one is not: every
  // step up to one past the furthest completed one is open, the rest wait their turn.
  const furthest = order.reduce((acc, k, i) => (done[k] ? i : acc), -1);
  const open = new Set(order.filter((k, i) => done[k] || i <= furthest + 1));
  const monthly =
    ch.plan_monthly_uzs ??
    plans.find((p) => p.id === ch.plan)?.monthly_uzs ??
    null;
  // Telegram is asked for the size as soon as the channel is added; the typed estimate is
  // only offered once that has failed (or has not answered within a few minutes).
  const calculating =
    !ch.quote && ch.preview_status === "pending" && !previewStale;
  const importPct =
    ch.progress.total && ch.progress.imported
      ? Math.min(
          100,
          Math.round((ch.progress.imported / ch.progress.total) * 100),
        )
      : 0;

  const skipButton = (
    <button
      className="btn-ghost"
      disabled={busy === "skip"}
      onClick={() =>
        void run("skip", () =>
          patch<SignupChannel>(`/api/signup/channels/${ch.id}`, {
            skip_verify: true,
          }),
        )
      }
    >
      {t("skipButton")}
    </button>
  );

  return (
    <section className="shell landing-section pt-10 sm:pt-14">
      <a
        href="/start"
        className="link-quiet inline-flex items-center gap-1.5 text-sm"
      >
        <ArrowLeftIcon size={14} /> {t("back")}
      </a>
      <div className="mt-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="landing-h2 mt-0">
          {ch.channel.username ? `@${ch.channel.username}` : ch.title}
        </h1>
        <span className="chip">{t(`status.${ch.status}` as never)}</span>
      </div>
      <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted-foreground">
        {ch.channel.title ? <span>{ch.channel.title}</span> : null}
        {ch.channel.participants_count ? (
          <span>
            {t("subscribers", {
              count: compactNumber(ch.channel.participants_count),
            })}
          </span>
        ) : null}
        <span>
          {t("siteAt")}:{" "}
          <strong className="text-foreground">{ch.domain}</strong>
        </span>
      </p>
      {error ? (
        <p className="mt-3 text-sm" style={{ color: "var(--destructive)" }}>
          {t("error", { message: error })}
        </p>
      ) : null}

      <ol className="flow">
        {/* 1 · size and price */}
        <Step
          k="estimate"
          done={done.estimate}
          open={open}
          title={t("steps.estimate")}
        >
          {ch.quote ? (
            <div className="flow-quote">
              <div>
                <span className="stat-value">
                  {compactNumber(ch.quote.posts)}
                </span>
                <span className="stat-label">
                  {t("posts", { count: compactNumber(ch.quote.posts) })} ·{" "}
                  {t(
                    `estimatedFrom.${ch.quote.source === "telegram" ? "telegram" : "manual"}`,
                  )}
                </span>
              </div>
              <div>
                <span className="stat-value">
                  {uzs(ch.quote.price_uzs)}{" "}
                  <small className="text-base font-semibold text-muted-foreground">
                    {t("currency")}
                  </small>
                </span>
                <span className="stat-label">{t("onboardingPrice")}</span>
              </div>
            </div>
          ) : calculating ? (
            <p className="flow-calculating text-sm text-muted-foreground">
              <span className="flow-spinner" aria-hidden />
              {t("calculating")}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t("estimateFailed")}
            </p>
          )}
          <p className="landing-note">{t("onboardingPriceHint")}</p>
          {!calculating && ch.quote?.source !== "telegram" && !requested ? (
            <form
              className="signup-add-row mt-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run("posts", () =>
                  patch<SignupChannel>(`/api/signup/channels/${ch.id}`, {
                    posts_estimate: Number(posts),
                  }),
                );
              }}
            >
              <input
                className="input-field"
                inputMode="numeric"
                placeholder={t("manualLabel")}
                aria-label={t("manualLabel")}
                value={posts}
                onChange={(e) => setPosts(e.target.value.replace(/\D/g, ""))}
              />
              <button
                className="btn-ghost"
                type="submit"
                disabled={!posts || busy === "posts"}
              >
                {t("manualButton")}
              </button>
            </form>
          ) : null}
        </Step>

        {/* 2 · prove ownership */}
        <Step
          k="verify"
          done={done.verify}
          open={open}
          title={t("steps.verify")}
        >
          {ch.verified ? (
            <p className="text-sm">{t("verified")}</p>
          ) : ch.verify_skipped ? (
            <p className="text-sm text-muted-foreground">{t("skipped")}</p>
          ) : botUsername && ch.channel.resolved ? (
            <>
              <p className="text-sm text-muted-foreground">
                {t("verifyBody", { bot: botUsername })}
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <button
                  className="btn-primary"
                  disabled={busy === "verify"}
                  onClick={() =>
                    void run("verify", async () => {
                      const r = await post<{ verified: boolean }>(
                        `/api/signup/channels/${ch.id}/verify`,
                      );
                      setVerifyResult(r.verified);
                      await refresh();
                    })
                  }
                >
                  {t("verifyButton")}
                </button>
                {skipButton}
                <span className="text-xs text-muted-foreground">
                  {t("verifyLater")}
                </span>
              </div>
              {verifyResult === false ? (
                <p className="mt-2 text-sm" style={{ color: "var(--warning)" }}>
                  {t("notVerified")}
                </p>
              ) : null}
            </>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                {t("verifyUnavailable")}
              </p>
              <div className="mt-3">{skipButton}</div>
            </>
          )}
        </Step>

        {/* 3 · plan */}
        <Step k="plan" done={done.plan} open={open} title={t("steps.plan")}>
          {requested ? (
            <p className="text-sm">
              <strong>{ch.plan ? t(`plans.${ch.plan}.name`) : "—"}</strong>
              {monthly !== null ? (
                <span className="text-muted-foreground">
                  {" "}
                  · {uzs(monthly)} {t("currency")}
                  {t("perMonth")}
                </span>
              ) : null}{" "}
              <span className="chip ml-2">{t("requested")}</span>
            </p>
          ) : (
            <>
              <p className="mb-3 text-sm text-muted-foreground">
                {t("choosePlan")}
              </p>
              <PlanCards
                plans={plans}
                selected={ch.plan}
                onSelect={(id: PlanId) =>
                  void run("plan", () =>
                    patch<SignupChannel>(`/api/signup/channels/${ch.id}`, {
                      plan: id,
                    }),
                  )
                }
              />
              {ch.plan && ch.quote ? (
                <dl className="flow-summary">
                  <dt>{t("summaryTitle")}</dt>
                  <dd />
                  <dt className="text-muted-foreground">
                    {t("summaryImport")}
                  </dt>
                  <dd>{uzs(ch.quote.price_uzs)}</dd>
                  <dt className="text-muted-foreground">
                    {t("summaryMonth", { plan: t(`plans.${ch.plan}.name`) })}
                  </dt>
                  <dd>{monthly !== null ? uzs(monthly) : "—"}</dd>
                  <dt>{t("summaryTotal")}</dt>
                  <dd>
                    {uzs(ch.quote.price_uzs + (monthly ?? 0))} {t("currency")}
                  </dd>
                </dl>
              ) : null}
              <button
                className="btn-primary mt-4"
                disabled={!ch.plan || !ch.quote || busy === "request"}
                onClick={() =>
                  void run("request", async () => {
                    const next = await post<SignupChannel>(
                      `/api/signup/channels/${ch.id}/request`,
                    );
                    router.refresh();
                    return next;
                  })
                }
              >
                <SendIcon size={16} />
                {t("requestButton")}
              </button>
            </>
          )}
        </Step>

        {/* 4 · payment, by hand through the admin */}
        <Step
          k="payment"
          done={done.payment}
          open={open}
          title={t("steps.payment")}
        >
          {paid ? (
            <p className="text-sm">
              {t("paid")}
              {ch.onboarding_paid_at ? (
                <span className="text-muted-foreground">
                  {" "}
                  · {fullDate(ch.onboarding_paid_at, locale)}
                </span>
              ) : null}
            </p>
          ) : requested ? (
            <>
              <p className="text-sm text-muted-foreground">
                {t("paymentBody", { name: t("awaitingPayment").toLowerCase() })}
              </p>
              {contactUrl ? (
                <a
                  href={contactUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-ghost mt-3"
                >
                  <SendIcon size={15} />
                  {t("contactAdmin")}
                </a>
              ) : null}
            </>
          ) : null}
        </Step>

        {/* 5 · import */}
        <Step
          k="import"
          done={done.import}
          open={open}
          title={t("steps.import")}
        >
          {imported ? (
            <p className="text-sm">
              {ch.status === "indexing"
                ? t("indexing")
                : t("importing", {
                    imported: compactNumber(ch.progress.imported),
                    total: compactNumber(
                      ch.progress.total ?? ch.progress.imported,
                    ),
                  })}
            </p>
          ) : ch.status === "backfilling" ? (
            <div className="max-w-sm">
              <p className="mb-1 text-sm">
                {t("importing", {
                  imported: compactNumber(ch.progress.imported),
                  total: ch.progress.total
                    ? compactNumber(ch.progress.total)
                    : "?",
                })}
              </p>
              <div className="h-[4px] overflow-hidden rounded-full bg-border">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${importPct}%` }}
                />
              </div>
            </div>
          ) : paid ? (
            <p className="text-sm text-muted-foreground">{t("importQueued")}</p>
          ) : null}
        </Step>

        {/* 6 · live */}
        <Step k="live" done={done.live} open={open} title={t("steps.live")}>
          {ch.status === "active" ? (
            <div className="flex flex-wrap items-center gap-3">
              <a
                href={ch.url}
                target="_blank"
                rel="noreferrer"
                className="btn-primary"
              >
                {t("openSite")} <ExternalIcon size={14} />
              </a>
              <a
                href={`${ch.url}studio`}
                target="_blank"
                rel="noreferrer"
                className="btn-ghost"
              >
                {t("openStudio")}
              </a>
              {ch.subscription_paid_until ? (
                <span className="text-xs text-muted-foreground">
                  {t("subscriptionUntil", {
                    date: fullDate(ch.subscription_paid_until, locale),
                  })}
                </span>
              ) : null}
            </div>
          ) : null}
        </Step>
      </ol>
    </section>
  );
}

function Step({
  k,
  done,
  open,
  title,
  children,
}: {
  k: StepKey;
  done: boolean;
  open: Set<StepKey>;
  title: string;
  children: React.ReactNode;
}) {
  const state = done ? "done" : open.has(k) ? "current" : "todo";
  return (
    <li className="flow-step" data-state={state}>
      <span className="flow-dot" aria-hidden>
        {done ? "✓" : ""}
      </span>
      <div className="flow-body">
        <h3>{title}</h3>
        {state === "todo" ? null : <div className="mt-2">{children}</div>}
      </div>
    </li>
  );
}
