import Link from "@/components/AppLink";
import { getTranslations } from "next-intl/server";
import { State } from "@/components/admin/StatusDot";
import { apiFetch } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { AdminSignup } from "@/lib/types";

export const dynamic = "force-dynamic";

/** Everyone who signed in on the platform domain, and what they asked for. */
export default async function SignupsPage() {
  const [signups, t] = await Promise.all([
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
                            import ${x.onboarding_quote.price_usd}
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
