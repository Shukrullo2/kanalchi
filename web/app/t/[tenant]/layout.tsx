import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/components/SiteHeader";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { TenantPublic } from "@/lib/types";

export default async function TenantLayout({ children }: { children: React.ReactNode }) {
  const [tenant, me, nav] = await Promise.all([
    apiFetchOrNull<TenantPublic>("/api/tenant"),
    getMe(),
    getTranslations("nav"),
  ]);
  if (!tenant) notFound();
  const isMember = me.authenticated && (me.role === "owner" || me.role === "editor");

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader
        title={tenant.title || tenant.domain}
        photoUrl={tenant.photo_url}
        items={[
          { href: "/", label: nav("home") },
          { href: "/tags", label: nav("tags") },
          { href: "/search", label: nav("search") },
          { href: "/stories", label: nav("stories") },
          { href: "/top", label: nav("top") },
          { href: "/chat", label: nav("chat") },
        ]}
        studio={isMember ? { href: "/studio", label: nav("studio") } : null}
      />

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6 sm:py-8">{children}</main>

      <footer className="mt-8 border-t">
        <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-6 text-xs text-muted-foreground">
          {tenant.username ? (
            <a href={`https://t.me/${tenant.username}`} target="_blank" rel="noreferrer" className="link-quiet">
              t.me/{tenant.username}
            </a>
          ) : null}
          <Link href="/stats" className="link-quiet">
            {nav("stats")}
          </Link>
          <Link href="/feed.xml" className="link-quiet">
            RSS
          </Link>
          <Link href="/studio" className="link-quiet ml-auto">
            {nav("studio")}
          </Link>
        </div>
      </footer>
    </div>
  );
}
