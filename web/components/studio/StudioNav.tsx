"use client";

import Link from "@/components/AppLink";
import { useTranslations } from "next-intl";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/studio", key: "dashboard", exact: true },
  { href: "/studio/ideas", key: "ideas" },
  { href: "/studio/drafts", key: "drafts" },
  { href: "/studio/research", key: "research" },
  { href: "/studio/settings", key: "settings" },
] as const;

export function StudioNav() {
  const t = useTranslations("studio.nav");
  const pathname = usePathname();
  return (
    <nav className="no-scrollbar mt-4 flex gap-6 overflow-x-auto border-b text-sm">
      {ITEMS.map((item) => {
        const active = "exact" in item && item.exact ? pathname === item.href : pathname.startsWith(item.href);
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
