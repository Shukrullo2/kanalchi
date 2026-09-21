import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { Avatar } from "@/components/Avatar";
import { Timeline } from "@/components/post/Timeline";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { compactNumber } from "@/lib/format";
import type { PostPage, TagOut, TenantPublic } from "@/lib/types";

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
  const [tenant, page, topTags, locale, t, tc] = await Promise.all([
    apiFetch<TenantPublic>("/api/tenant"),
    apiFetch<PostPage>("/api/posts?limit=20"),
    apiFetchOrNull<TagOut[]>("/api/tags?limit=12"),
    getLocale(),
    getTranslations("home"),
    getTranslations("common"),
  ]);

  return (
    <div className="space-y-6">
      <section className="flex items-start gap-4">
        <Avatar src={tenant.photo_url} name={tenant.title || tenant.domain} size={56} />
        <div className="min-w-0 flex-1">
          <h1 className="text-balance text-2xl font-semibold tracking-tight">{tenant.title || tenant.domain}</h1>
          {tenant.about ? <p className="mt-1 text-pretty text-sm text-muted-foreground">{tenant.about}</p> : null}
          <p className="meta-row mt-2">
            <span>{tc("posts", { count: tenant.post_count ?? 0 })}</span>
            {tenant.participants_count ? (
              <span className="divider-dot">{compactNumber(tenant.participants_count)} subscribers</span>
            ) : null}
          </p>
        </div>
      </section>

      {topTags && topTags.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {topTags.map((tag) => (
            <TagChip key={tag.slug} tag={tag} locale={locale} showCount />
          ))}
        </div>
      ) : null}

      {page.items.length === 0 ? (
        <div className="card-surface flex flex-col items-center gap-2 p-12 text-center">
          <h2 className="font-medium">{t("emptyTitle")}</h2>
          <p className="max-w-sm text-sm text-muted-foreground">{t("emptyBody")}</p>
        </div>
      ) : (
        <Timeline initial={page} loadMoreLabel={tc("loadMore")} />
      )}
    </div>
  );
}
