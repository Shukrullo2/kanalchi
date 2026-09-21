"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Avatar } from "@/components/Avatar";
import { CloseIcon, MenuIcon } from "@/components/Icons";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { ThemeToggle } from "@/components/ThemeToggle";

export type NavItem = { href: string; label: string };

export function SiteHeader({
  title,
  photoUrl,
  items,
  studio,
}: {
  title: string;
  photoUrl?: string | null;
  items: NavItem[];
  studio?: { href: string; label: string } | null;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <header className="glass sticky top-0 z-40 border-b">
      <div className="shell flex h-14 items-center gap-3">
        <Link href="/" className="flex min-w-0 items-center gap-2.5">
          <Avatar src={photoUrl} name={title} size={26} />
          <span className="truncate text-[0.9375rem] font-medium tracking-tight">{title}</span>
        </Link>

        <nav className="ml-auto hidden items-center gap-6 sm:flex">
          {items.map((item) => (
            <Link key={item.href} href={item.href} className="nav-link" data-active={isActive(item.href)}>
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-1 sm:ml-3">
          {studio ? (
            <Link
              href={studio.href}
              className="hidden rounded-full border px-3 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground sm:inline-flex"
            >
              {studio.label}
            </Link>
          ) : null}
          <LocaleSwitch />
          <ThemeToggle />
          <button
            className="grid h-8 w-8 place-items-center rounded-full text-muted-foreground hover:bg-surface-2 sm:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Menu"
            aria-expanded={open}
          >
            {open ? <CloseIcon size={18} /> : <MenuIcon size={18} />}
          </button>
        </div>
      </div>

      {open ? (
        <nav className="border-t sm:hidden">
          <div className="shell py-1.5">
            {[...items, ...(studio ? [studio] : [])].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className="block py-2 text-sm"
                data-active={isActive(item.href)}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
