import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { State } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import { compactNumber, uzs } from "@/lib/format";
import type { AdminChannelQuote, AdminSignup } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Channels priced on osor.uz/start (no sign-in needed), and the people who signed in there before that. */
export default async function SignupsPage() {
  const [quotes, signups, t] = await Promise.all([
    apiFetch<AdminChannelQuote[]>("/api/admin/quotes", { admin: true }),
    apiFetch<AdminSignup[]>("/api/admin/signups", { admin: true }),
    getTranslations("admin"),
  ]);
  const pending = signups
    .flatMap((s) => s.tenants)
    .filter((x) => x.subscription_status === "pending").length;

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 border-b pb-4">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">
          {t("signups")}
        </h1>
        <span className="text-sm text-muted-foreground">
          {signups.length} signed up · {pending} awaiting payment
        </span>
      </div>

      <QuoteList quotes={quotes} />

      <h2 className="mt-10 border-b pb-3 text-lg font-semibold">Signed in (old flow)</h2>
      {signups.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">
          Nobody has signed up on the platform domain yet.
        </p>
      ) : (
        <ul className="rows">
          {signups.map((u) => (
            <li key={u.user_id} className="row">
              <span className="row-margin text-xs text-muted-foreground">
                {new Date(u.signed_up_at).toISOString().slice(0, 10)}
              </span>
              <div className="row-body">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="text-[0.9375rem] font-medium">{u.name}</span>
                  {u.username ? (
                    <a
                      href={`https://t.me/${u.username}`}
                      target="_blank"
                      rel="noreferrer"
                      className="link-quiet text-xs"
                    >
                      @{u.username}
                    </a>
                  ) : null}
                  <span className="tnum text-xs text-muted-foreground">
                    tg {u.tg_user_id}
                  </span>
                </div>
                {u.tenants.length === 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">
                    No channel added yet.
                  </p>
                ) : (
                  <ul className="mt-2 space-y-1.5">
                    {u.tenants.map((x) => (
                      <li
                        key={x.id}
                        className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
                      >
                        <State status={x.status} />
                        <Link
                          href={`/tenants/${x.id}`}
                          className="font-medium hover:text-primary"
                        >
                          {x.channel?.username
                            ? `@${x.channel.username}`
                            : x.domain}
                        </Link>
                        <span className="text-xs text-muted-foreground">
                          {x.domain}
                        </span>
                        {x.channel?.backfill_total_estimate ? (
                          <span className="tnum text-xs text-muted-foreground">
                            {compactNumber(x.channel.backfill_total_estimate)}{" "}
                            posts
                          </span>
                        ) : null}
                        <span className="chip">{x.plan ?? "no plan"}</span>
                        <span
                          className="text-xs"
                          style={{
                            color:
                              x.subscription_status === "pending"
                                ? "var(--warning)"
                                : "var(--muted-foreground)",
                          }}
                        >
                          {x.subscription_status}
                        </span>
                        {x.onboarding_quote ? (
                          <span className="tnum text-xs text-muted-foreground">
                            import {uzs(x.onboarding_quote.price_uzs)} UZS
                          </span>
                        ) : null}
                        {x.onboarding_paid_at ? (
                          <span className="text-xs text-muted-foreground">
                            paid
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function QuoteList({ quotes }: { quotes: AdminChannelQuote[] }) {
  if (quotes.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Nobody has priced a channel yet.
      </p>
    );
  }
  return (
    <ul className="rows">
      {quotes.map((q) => (
        <li key={q.username} className="row">
          <span className="row-margin text-xs text-muted-foreground">
            {new Date(q.updated_at).toISOString().slice(0, 10)}
          </span>
          <div className="row-body">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
              <a
                href={`https://t.me/${q.username}`}
                target="_blank"
                rel="noreferrer"
                className="text-[0.9375rem] font-medium hover:text-primary"
              >
                @{q.username}
              </a>
              {q.title ? <span className="text-muted-foreground">{q.title}</span> : null}
              {q.participants_count ? (
                <span className="tnum text-xs text-muted-foreground">
                  {compactNumber(q.participants_count)} subscribers
                </span>
              ) : null}
              {q.times_asked > 1 ? (
                <span className="tnum text-xs text-muted-foreground">asked {q.times_asked}×</span>
              ) : null}
              <State status={q.status === "done" ? "active" : q.status === "failed" ? "error" : "onboarding"} label={q.status} />
            </div>
            {q.quote ? (
              <p className="tnum mt-1 text-xs text-muted-foreground">
                {compactNumber(q.quote.posts)} posts ({q.quote.source}) · import{" "}
                <span className="text-foreground">{uzs(q.quote.price_uzs)} UZS</span> · AI ≈ $
                {q.quote.ai_usd} · margin {uzs(q.quote.margin_uzs ?? 0)} UZS
              </p>
            ) : null}
            {q.error ? (
              <p className="mt-1 text-xs" style={{ color: "var(--warning)" }}>
                {q.error}
              </p>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
