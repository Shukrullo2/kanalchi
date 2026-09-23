import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";
import { SiteHeader } from "@/components/SiteHeader";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { TenantPublic } from "@/lib/types";

export default async function TenantLayout({ children }: { children: React.ReactNode }) {
  const [tenant, me, nav, common] = await Promise.all([
    apiFetchOrNull<TenantPublic>("/api/tenant"),
    getMe(),
    getTranslations("nav"),
    getTranslations("common"),
  ]);
  if (!tenant) notFound();
  const isMember = me.authenticated && (me.role === "owner" || me.role === "editor");

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader
        title={tenant.title || tenant.domain}
        photoUrl={tenant.photo_url}
        items={[
          { href: "/posts", label: nav("posts") },
          { href: "/tags", label: nav("tags") },
          { href: "/graph", label: nav("graph") },
          { href: "/search", label: nav("search") },
          { href: "/stories", label: nav("stories") },
          { href: "/top", label: nav("top") },
          { href: "/chat", label: nav("chat") },
        ]}
        studio={isMember ? { href: "/studio", label: nav("studio") } : null}
        menuLabel={common("menu")}
        themeLabel={common("theme")}
      />

      <main className="shell flex-1 pb-10 pt-6">{children}</main>

      <footer className="mt-12 border-t">
        <div className="shell flex flex-wrap items-center gap-x-5 gap-y-2 py-6 text-xs text-muted-foreground">
          {tenant.username ? (
            <a href={`https://t.me/${tenant.username}`} target="_blank" rel="noreferrer" className="link-quiet">
              t.me/{tenant.username}
            </a>
          ) : null}
          <Link href="/feed.xml" className="link-quiet">
            RSS
          </Link>
          <Link href="/studio" className="link-quiet ml-auto">
            {nav("studio")}
          </Link>
          <span>{common("madeBy")}</span>
        </div>
      </footer>
    </div>
  );
}
