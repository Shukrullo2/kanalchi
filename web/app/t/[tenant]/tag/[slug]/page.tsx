import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getLocale } from "next-intl/server";
import { ArrowRightIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { Histogram } from "@/components/tags/Histogram";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { tagLabel } from "@/lib/labels";
import type { EntitySummaryOut, SearchResult, TagDetail, TenantPublic } from "@/lib/types";

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

  const [results, summary] = await Promise.all([
    apiFetch<SearchResult>(`/api/search?tags=${encodeURIComponent(slug)}&sort=newest&limit=20&with_facets=false`),
    apiFetchOrNull<EntitySummaryOut>(`/api/tags/${encodeURIComponent(slug)}/summary`),
  ]);
  const tone = `var(--dim-${tag.dimension ?? "default"}, var(--dim-default))`;
  const years =
    tag.first_post_at && tag.last_post_at
      ? `${new Date(tag.first_post_at).getFullYear()}–${new Date(tag.last_post_at).getFullYear()}`
      : null;

  return (
    <div className="space-y-5">
      <header className="card-surface space-y-3 p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <span className="mt-2 inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: tone }} aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-2">
              <h1 className="text-balance text-xl font-semibold tracking-tight">{tagLabel(tag, locale)}</h1>
              {tag.dimension ? (
                <Link href={`/tags/${tag.dimension}`} className="text-xs text-muted-foreground hover:text-foreground">
                  {tag.dimension}
                </Link>
              ) : null}
            </div>
            {tag.description ? <p className="mt-1 text-pretty text-sm text-muted-foreground">{tag.description}</p> : null}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center sm:max-w-sm">
          <div className="stat-tile">
            <div className="stat-value">{tag.post_count}</div>
            <div className="stat-label">posts</div>
          </div>
          {years ? (
            <div className="stat-tile">
              <div className="stat-value text-base">{years}</div>
              <div className="stat-label">covered</div>
            </div>
          ) : null}
          {tag.engagement_score ? (
            <div className="stat-tile">
              <div className="stat-value">{tag.engagement_score}×</div>
              <div className="stat-label">reach</div>
            </div>
          ) : null}
        </div>

        <Histogram data={tag.histogram} tone={tag.dimension ?? undefined} locale={locale} />

        {tag.parent || tag.children.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5 border-t pt-3">
            {tag.parent ? (
              <>
                <span className="text-xs text-muted-foreground">part of</span>
                <TagChip tag={tag.parent} locale={locale} />
              </>
            ) : null}
            {tag.children.map((c) => (
              <TagChip key={c.slug} tag={c} locale={locale} showCount />
            ))}
          </div>
        ) : null}

        {tag.co_tags.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5 border-t pt-3">
            <span className="text-xs text-muted-foreground">often with</span>
            {tag.co_tags.slice(0, 8).map((c) => (
              <Link key={c.slug} href={`/tag/${c.slug}`} className="chip hover:bg-border">
                {c.labels?.[locale] || c.name}
                <span className="tag-count">{c.count}</span>
              </Link>
            ))}
          </div>
        ) : null}
      </header>

      {summary?.available ? (
        <section className="card-surface p-4 sm:p-5">
          <h2 className="mb-1.5 text-xs uppercase tracking-wider text-muted-foreground">
            What this channel has said
          </h2>
          <p className="text-pretty text-sm leading-relaxed">
            {summary.summary[locale] ?? summary.summary.en}
          </p>
          {summary.citations.length > 0 ? (
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {summary.citations.slice(0, 8).map((id) => (
                <Link key={id} href={`/post/${id}`} className="chip hover:bg-border">
                  #{id}
                </Link>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="space-y-3.5">
        {results.items.map((p, i) => (
          <div key={p.id} className="animate-rise" style={{ animationDelay: `${Math.min(i, 8) * 25}ms` }}>
            <PostCard post={p} locale={locale} />
          </div>
        ))}
      </div>

      {results.has_more ? (
        <Link href={`/search?tags=${encodeURIComponent(slug)}`} className="btn-ghost w-full justify-center">
          see all {tag.post_count} posts <ArrowRightIcon size={14} />
        </Link>
      ) : null}
    </div>
  );
}
