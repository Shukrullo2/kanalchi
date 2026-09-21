import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { Timeline } from "@/components/post/Timeline";
import { apiFetch } from "@/lib/api";
import type { PostPage, TenantPublic } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const tenant = await apiFetch<TenantPublic>("/api/tenant");
  return {
    title: tenant.title || tenant.domain,
    description: tenant.about ?? undefined,
    alternates: { types: { "application/rss+xml": "/feed.xml" } },
    openGraph: { title: tenant.title, description: tenant.about ?? undefined, type: "website" },
  };
}

export default async function TenantHome() {
  const [tenant, page, t, tc] = await Promise.all([
    apiFetch<TenantPublic>("/api/tenant"),
    apiFetch<PostPage>("/api/posts?limit=20"),
    getTranslations("home"),
    getTranslations("common"),
  ]);

  return (
    <div className="space-y-4">
      {tenant.about ? <p className="text-sm text-muted-foreground">{tenant.about}</p> : null}
      <p className="text-xs text-muted-foreground">{tc("posts", { count: tenant.post_count ?? 0 })}</p>
      {page.items.length === 0 ? (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <h2 className="font-medium">{t("emptyTitle")}</h2>
          <p className="text-sm text-muted-foreground">{t("emptyBody")}</p>
        </div>
      ) : (
        <Timeline initial={page} loadMoreLabel={tc("loadMore")} />
      )}
    </div>
  );
}
