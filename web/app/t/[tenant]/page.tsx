import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { Timeline } from "@/components/post/Timeline";
import { ChannelIndex } from "@/components/tags/ChannelIndex";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { compactNumber, dateSpan } from "@/lib/format";
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
    apiFetchOrNull<TagOut[]>("/api/tags?limit=40"),
    getLocale(),
    getTranslations("home"),
    getTranslations("common"),
  ]);

  const span =
    tenant.first_post_at && tenant.last_post_at
      ? dateSpan(tenant.first_post_at, tenant.last_post_at, locale)
      : null;

  return (
    <div>
      <header className="pb-6">
        <h1 className="text-balance text-[1.75rem] font-semibold tracking-tight sm:text-[2.125rem]">
          {tenant.title || tenant.domain}
        </h1>
        {tenant.about ? (
          <p className="mt-2 max-w-[60ch] text-pretty text-[0.9375rem] text-muted-foreground">{tenant.about}</p>
        ) : null}
        <p className="meta-row mt-3">
          <span>{tc("posts", { count: tenant.post_count ?? 0 })}</span>
          {span ? <span suppressHydrationWarning>{span}</span> : null}
          {tenant.participants_count ? (
            <span>{t("subscribers", { count: compactNumber(tenant.participants_count) })}</span>
          ) : null}
        </p>
      </header>

      {topTags && topTags.length > 0 ? (
        <ChannelIndex
          tags={topTags}
          locale={locale}
          headings={{ themes: t("indexThemes"), entities: t("indexEntities"), all: t("indexAll") }}
        />
      ) : null}

      {page.items.length === 0 ? (
        <div className="py-16 text-center">
          <h2 className="font-medium">{t("emptyTitle")}</h2>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">{t("emptyBody")}</p>
        </div>
      ) : (
        <div className="mt-2">
          <Timeline initial={page} loadMoreLabel={tc("loadMore")} />
        </div>
      )}
    </div>
  );
}
