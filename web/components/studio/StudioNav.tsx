"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/studio", label: "Dashboard", exact: true },
  { href: "/studio/ideas", label: "Ideas" },
  { href: "/studio/drafts", label: "Drafts" },
  { href: "/studio/research", label: "Research" },
  { href: "/studio/tags", label: "Tags" },
  { href: "/studio/settings", label: "Settings" },
];

export function StudioNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto rounded-full bg-surface-2 p-1 text-sm">
      {ITEMS.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`whitespace-nowrap rounded-full px-3 py-1.5 transition-colors ${
              active ? "bg-surface font-medium shadow-xs" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
