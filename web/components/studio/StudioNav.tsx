"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/studio", label: "Dashboard", exact: true },
  { href: "/studio/ideas", label: "Ideas" },
  { href: "/studio/drafts", label: "Drafts" },
  { href: "/studio/research", label: "Research" },
  { href: "/studio/tags", label: "Index" },
  { href: "/studio/settings", label: "Settings" },
];

export function StudioNav() {
  const pathname = usePathname();
  return (
    <nav className="no-scrollbar mt-4 flex gap-6 overflow-x-auto border-b text-sm">
      {ITEMS.map((item) => {
        const active = item.exact ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className="nav-link nav-tab whitespace-nowrap"
            data-active={active}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
