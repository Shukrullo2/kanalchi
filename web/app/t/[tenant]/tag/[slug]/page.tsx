import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getLocale } from "next-intl/server";
import { Histogram } from "@/components/tags/Histogram";
import { PostCard } from "@/components/post/PostCard";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { tagLabel } from "@/lib/labels";
import type { SearchResult, TagDetail, TenantPublic } from "@/lib/types";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const [tag, tenant] = await Promise.all([
    apiFetchOrNull<TagDetail>(`/api/tags/${slug}`),
    apiFetchOrNull<TenantPublic>("/api/tenant"),
  ]);
  if (!tag || tag.redirect_to) return { title: "Tag" };
  return {
    title: `${tag.name} · ${tenant?.title ?? ""}`,
    description: tag.description ?? `${tag.post_count} posts about ${tag.name}`,
  };
}

export default async function TagPage({ params }: Props) {
  const { slug } = await params;
  const [tag, locale] = await Promise.all([apiFetchOrNull<TagDetail>(`/api/tags/${slug}`), getLocale()]);
  if (!tag) notFound();
  if (tag.redirect_to) redirect(`/tag/${tag.redirect_to}`);

  const results = await apiFetch<SearchResult>(
    `/api/search?tags=${encodeURIComponent(slug)}&sort=newest&limit=20&with_facets=false`,
  );

  return (
    <div className="space-y-5">
      <header className="space-y-2">
        <h1 className="text-xl font-medium">{tagLabel(tag, locale)}</h1>
        {tag.description ? <p className="text-sm text-muted-foreground">{tag.description}</p> : null}
        <p className="text-xs text-muted-foreground">
          {tag.post_count} posts
          {tag.first_post_at
            ? ` · ${new Date(tag.first_post_at).getFullYear()}–${new Date(tag.last_post_at ?? tag.first_post_at).getFullYear()}`
            : null}
          {tag.engagement_score ? ` · ${tag.engagement_score}× average reach` : null}
        </p>
        <Histogram data={tag.histogram} />
      </header>

      {tag.parent || tag.children.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          {tag.parent ? (
            <>
              <span className="text-muted-foreground">in</span>
              <TagChip tag={tag.parent} locale={locale} />
            </>
          ) : null}
          {tag.children.map((c) => (
            <TagChip key={c.slug} tag={c} locale={locale} showCount />
          ))}
        </div>
      ) : null}

      {tag.co_tags.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">often with</span>
          {tag.co_tags.slice(0, 8).map((c) => (
            <Link key={c.slug} href={`/tag/${c.slug}`} className="rounded-full border px-2.5 py-0.5 text-xs hover:bg-muted">
              {c.labels?.[locale] || c.name} <span className="text-muted-foreground">{c.count}</span>
            </Link>
          ))}
        </div>
      ) : null}

      <div>
        {results.items.map((p) => (
          <PostCard key={p.id} post={p} />
        ))}
      </div>
      {results.has_more ? (
        <Link href={`/search?tags=${encodeURIComponent(slug)}`} className="inline-block text-sm underline">
          see all →
        </Link>
      ) : null}
    </div>
  );
}
