import Link from "next/link";
import { getTranslations } from "next-intl/server";
import { notFound } from "next/navigation";
import { LocaleSwitch } from "@/components/LocaleSwitch";
import { apiFetchOrNull } from "@/lib/api";
import { getMe } from "@/lib/auth";
import type { TenantPublic } from "@/lib/types";

export default async function TenantLayout({ children }: { children: React.ReactNode }) {
  const [tenant, me, t] = await Promise.all([apiFetchOrNull<TenantPublic>("/api/tenant"), getMe(), getTranslations("nav")]);
  if (!tenant) notFound();
  const isMember = me.authenticated && (me.role === "owner" || me.role === "editor");
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-4">
      <header className="flex items-center justify-between gap-4 border-b py-4">
        <Link href="/" className="text-lg font-semibold">
          {tenant.title || tenant.domain}
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/">{t("home")}</Link>
          <Link href="/tags">{t("tags")}</Link>
          <Link href="/search">{t("search")}</Link>
          <Link href="/top">{t("top")}</Link>
          <Link href="/chat">{t("chat")}</Link>
          {isMember ? (
            <Link href="/studio" className="font-medium">
              {t("studio")}
            </Link>
          ) : null}
          <LocaleSwitch />
        </nav>
      </header>
      <main className="flex-1 py-6">{children}</main>
      <footer className="border-t py-4 text-xs text-muted-foreground">
        {tenant.username ? (
          <a href={`https://t.me/${tenant.username}`} target="_blank" rel="noreferrer">
            t.me/{tenant.username}
          </a>
        ) : null}
        <span className="float-right">
          <Link href="/studio">{t("studio")}</Link>
        </span>
      </footer>
    </div>
  );
}
