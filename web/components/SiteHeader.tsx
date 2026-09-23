"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Avatar } from "@/components/Avatar";
import { CloseIcon, MenuIcon } from "@/components/Icons";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { ThemeToggle } from "@/components/ThemeToggle";

export type NavItem = { href: string; label: string };

/** A floating bar: rounded, lifted off the page, sticky. */
export function SiteHeader({
  title,
  photoUrl,
  items,
  studio,
  menuLabel,
  themeLabel,
}: {
  title: string;
  photoUrl?: string | null;
  items: NavItem[];
  studio?: { href: string; label: string } | null;
  menuLabel: string;
  themeLabel: string;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="sticky top-0 z-40 pt-3">
      <div className="shell">
        <header className="topbar">
          <Link href="/" className="flex min-w-0 items-center gap-2.5">
            <Avatar src={photoUrl} name={title} size={30} />
            <span className="truncate font-display text-[1.05rem] font-bold tracking-tight">{title}</span>
          </Link>

          <nav className="ml-auto hidden items-center gap-6 lg:flex">
            {items.map((item) => (
              <Link key={item.href} href={item.href} className="nav-link" data-active={isActive(item.href)}>
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-1.5 lg:ml-4">
            {studio ? (
              <Link href={studio.href} className="pill hidden py-1.5 text-xs sm:inline-flex">
                {studio.label}
              </Link>
            ) : null}
            <LocaleSwitch />
            <ThemeToggle label={themeLabel} />
            <button
              className="grid h-9 w-9 place-items-center rounded-lg border border-border-strong text-muted-foreground hover:text-foreground lg:hidden"
              onClick={() => setOpen((v) => !v)}
              aria-label={menuLabel}
              aria-expanded={open}
            >
              {open ? <CloseIcon size={18} /> : <MenuIcon size={18} />}
            </button>
          </div>
        </header>

        {open ? (
          <nav className="topbar mt-2 flex-col items-stretch gap-0 py-2 lg:hidden">
            {[...items, ...(studio ? [studio] : [])].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-2.5 text-[0.9375rem] font-medium hover:bg-surface-2"
                data-active={isActive(item.href)}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        ) : null}
      </div>
    </div>
  );
}
