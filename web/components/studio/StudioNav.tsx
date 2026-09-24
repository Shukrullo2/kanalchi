"use client";

import Link from "@/components/AppLink";
import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/studio", key: "dashboard", exact: true },
  { href: "/studio/ideas", key: "ideas" },
  { href: "/studio/drafts", key: "drafts" },
  { href: "/studio/research", key: "research" },
  // The channel watcher (daily digests of channels the blogger follows) is promised on
  // Premium but not built yet; the tab says so instead of leading anywhere.
  { href: "/studio/watcher", key: "watcher", soon: true },
  { href: "/studio/settings", key: "settings" },
] as const;

export function StudioNav() {
  const t = useTranslations("studio.nav");
  const common = useTranslations("common");
  const pathname = usePathname();
  return (
    <nav className="no-scrollbar mt-4 flex gap-6 overflow-x-auto border-b text-sm">
      {ITEMS.map((item) => {
        const active =
          "exact" in item && item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href);
        if ("soon" in item && item.soon) {
          return (
            <span
              key={item.href}
              className="nav-link nav-tab whitespace-nowrap opacity-60"
              aria-disabled
              title={common("comingSoon")}
            >
              {t(item.key)}{" "}
              <span className="plan-soon">{common("comingSoon")}</span>
            </span>
          );
        }
        return (
          <Link
            key={item.href}
            href={item.href}
            className="nav-link nav-tab whitespace-nowrap"
            data-active={active}
          >
            {t(item.key)}
          </Link>
        );
      })}
    </nav>
  );
}
