import type { Metadata } from "next";
import { getLocale, getTranslations } from "next-intl/server";
import { ArchiveControls } from "@/components/ArchiveControls";
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

/** 12948 → "12 948": a thin space per thousand, the same in every locale we serve. */
function groupThousands(n: number): string {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/** A Telegram bio is often a list of "Label: url" pairs; drop the URLs and any label left dangling. */
function cleanAbout(about: string): string {
  return about
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\S+:\s*(?=\S+:|$)/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/** "Bakiroo arxivi" → the last word in gold, so the headline has a second colour. */
function splitTitle(title: string): [string, string] {
  const words = title.trim().split(/\s+/);
  if (words.length < 2) return [title, ""];
  return [words.slice(0, -1).join(" ") + " ", words[words.length - 1]];
}

export default async function TenantHome() {
  const [tenant, page, topTags, locale, t, tc] = await Promise.all([
    apiFetch<TenantPublic>("/api/tenant"),
    apiFetch<PostPage>("/api/posts?limit=24"),
    apiFetchOrNull<TagOut[]>("/api/tags?limit=40"),
    getLocale(),
    getTranslations("home"),
    getTranslations("common"),
  ]);

  const title = tenant.title || tenant.domain;
  const [head, tail] = splitTitle(title);
  const span =
    tenant.first_post_at && tenant.last_post_at
      ? dateSpan(tenant.first_post_at, tenant.last_post_at, locale)
      : null;

  return (
    <div>
      <header className="py-8 text-center sm:py-12">
        {tenant.username ? <p className="eyebrow">@{tenant.username}</p> : null}
        <h1 className="hero-title mt-3">
          {head}
          {tail ? <span className="hero-accent">{tail}</span> : null}
        </h1>
        {tenant.about ? (
          <p className="mx-auto mt-5 line-clamp-2 max-w-[56ch] text-pretty text-[0.9375rem] text-muted-foreground">
            {cleanAbout(tenant.about)}
          </p>
        ) : null}
        <p className="meta-row mt-4 justify-center">
          {span ? <span suppressHydrationWarning>{span}</span> : null}
          {tenant.participants_count ? (
            <span>{t("subscribers", { count: compactNumber(tenant.participants_count) })}</span>
          ) : null}
        </p>
      </header>

      <div className="border-b pb-5">
        <ArchiveControls
          placeholder={t("searchPlaceholder")}
          sorts={[
            { href: "/", label: t("sortNewest"), active: true },
            { href: "/top", label: t("sortTop") },
          ]}
          totalLabel={t("totalPosts", { count: groupThousands(tenant.post_count ?? 0) })}
        />
      </div>

      {topTags && topTags.length > 0 ? (
        <div className="mt-6">
          <ChannelIndex
            tags={topTags}
            locale={locale}
            headings={{ themes: t("indexThemes"), entities: t("indexEntities"), all: t("indexAll") }}
          />
        </div>
      ) : null}

      {page.items.length === 0 ? (
        <div className="py-16 text-center">
          <h2 className="text-xl">{t("emptyTitle")}</h2>
          <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">{t("emptyBody")}</p>
        </div>
      ) : (
        <div className="mt-6">
          <Timeline initial={page} loadMoreLabel={tc("loadMore")} />
        </div>
      )}
    </div>
  );
}
