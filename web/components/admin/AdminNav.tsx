"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SparkIcon } from "@/components/Icons";
import { SignOut } from "@/components/SignOut";
import { ThemeToggle } from "@/components/ThemeToggle";

export function AdminNav({
  name,
  items,
  onboardLabel,
}: {
  name: string;
  items: { href: string; label: string }[];
  onboardLabel: string;
}) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <header className="glass sticky top-0 z-40 border-b">
      <div className="mx-auto flex h-14 w-full max-w-5xl items-center gap-4 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-primary text-xs text-primary-foreground">K</span>
          <span className="hidden sm:inline">Kanalchi</span>
        </Link>

        <nav className="flex items-center gap-4 overflow-x-auto">
          {items.map((item) => (
            <Link key={item.href} href={item.href} className="nav-link whitespace-nowrap" data-active={isActive(item.href)}>
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <Link href="/onboard" className="btn-primary hidden py-1.5 text-xs sm:inline-flex">
            <SparkIcon size={13} />
            {onboardLabel}
          </Link>
          <span className="hidden text-xs text-muted-foreground md:inline">{name}</span>
          <ThemeToggle />
          <SignOut label="↪" />
        </div>
      </div>
    </header>
  );
}
