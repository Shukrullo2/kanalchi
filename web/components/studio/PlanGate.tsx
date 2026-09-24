"use client";

import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";

/** The studio pages that are the premium plan's writing tools. */
const GATED = ["/studio/ideas", "/studio/drafts", "/studio/research"];

/**
 * On a plan without the writing tools, the gated pages show what Premium adds instead of
 * their content; the dashboard and settings stay open. The API refuses those calls too
 * (402), so this is the friendly face, not the lock.
 */
export function PlanGate({
  writingTools,
  plansUrl,
  children,
}: {
  writingTools: boolean;
  plansUrl: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("studio.planGate");
  const pathname = usePathname();
  if (writingTools || !GATED.some((p) => pathname.startsWith(p)))
    return <>{children}</>;
  return (
    <div className="card-surface mx-auto max-w-lg space-y-3 p-6 text-center">
      <h2 className="text-lg font-bold">{t("title")}</h2>
      <p className="text-sm text-muted-foreground">{t("body")}</p>
      <a
        href={plansUrl}
        target="_blank"
        rel="noreferrer"
        className="btn-primary"
      >
        {t("cta")}
      </a>
    </div>
  );
}
