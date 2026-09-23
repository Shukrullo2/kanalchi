import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { ArrowRightIcon } from "@/components/Icons";
import { PostCard } from "@/components/post/PostCard";
import { Histogram } from "@/components/tags/Histogram";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch, apiFetchOrNull } from "@/lib/api";
import { dimensionLabel, tagDescription, tagLabel } from "@/lib/labels";
import type { DimensionOut, EntitySummaryOut, SearchResult, TagDetail, TenantPublic } from "@/lib/types";
import { tierOf, toneVar } from "@/lib/dimensions";

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const [tag, tenant, locale, t] = await Promise.all([
    apiFetchOrNull<TagDetail>(`/api/tags/${slug}`),
    apiFetchOrNull<TenantPublic>("/api/tenant"),
    getLocale(),
    getTranslations("tag"),
  ]);
  if (!tag || tag.redirect_to) return { title: t("title") };
  const name = tagLabel(tag, locale);
  return {
    title: `${name} · ${tenant?.title ?? ""}`,
    description: tagDescription(tag, locale) ?? t("seeAll", { count: tag.post_count }),
  };
}

export default async function TagPage({ params }: Props) {
  const { slug } = await params;
  const [tag, locale, t, g] = await Promise.all([
    apiFetchOrNull<TagDetail>(`/api/tags/${slug}`),
    getLocale(),
    getTranslations("tag"),
    getTranslations("graph"),
  ]);
  if (!tag) notFound();
  if (tag.redirect_to) redirect(`/tag/${tag.redirect_to}`);

  const [results, summary, dimensions] = await Promise.all([
    apiFetch<SearchResult>(`/api/search?tags=${encodeURIComponent(slug)}&sort=newest&limit=20&with_facets=false`),
    apiFetchOrNull<EntitySummaryOut>(`/api/tags/${encodeURIComponent(slug)}/summary`),
    apiFetchOrNull<DimensionOut[]>("/api/dimensions"),
  ]);
  const tone = toneVar(tag.dimension);
  const group = dimensions?.find((d) => d.key === tag.dimension) ?? null;
  const description = tagDescription(tag, locale);
  const firstYear = tag.first_post_at ? new Date(tag.first_post_at).getFullYear() : null;
  const lastYear = tag.last_post_at ? new Date(tag.last_post_at).getFullYear() : null;
  const years = firstYear && lastYear ? (firstYear === lastYear ? `${firstYear}` : `${firstYear}–${lastYear}`) : null;
  const coTags = tag.co_tags.filter((c) => tierOf(c.dimension) !== "meta");

  return (
    <div>
      <header className="space-y-4 border-b pb-6">
        <div className="flex items-start gap-3">
          <span className="mt-3 inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: tone }} aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-2.5">
              <h1 className="text-balance text-[1.75rem] font-semibold tracking-tight">{tagLabel(tag, locale)}</h1>
              {tag.dimension ? (
                <Link href={`/tags/${tag.dimension}`} className="text-xs text-muted-foreground hover:text-foreground">
                  {group ? dimensionLabel(group, locale) : tag.dimension}
                </Link>
              ) : null}
            </div>
            {description ? <p className="mt-1 text-pretty text-sm text-muted-foreground">{description}</p> : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-x-10 gap-y-3">
          <div className="stat-tile">
            <div className="stat-value">{tag.post_count}</div>
            <div className="stat-label">{t("posts")}</div>
          </div>
          {years ? (
            <div className="stat-tile">
              <div className="stat-value text-[1.25rem]">{years}</div>
              <div className="stat-label">{firstYear === lastYear ? t("year") : t("years")}</div>
            </div>
          ) : null}
          {tag.engagement_score ? (
            <div className="stat-tile">
              <div className="stat-value">{tag.engagement_score}×</div>
              <div className="stat-label">{t("ofAverage")}</div>
            </div>
          ) : null}
        </div>

        <Histogram data={tag.histogram} tone={tag.dimension ?? undefined} locale={locale} />

        {/* Only for a subject the map actually draws. Filing tags — language,
            format, stance and the rest of the meta tier — are left out of the
            map's payload, so a link from one of their pages could only ever
            land on an empty map. */}
        {tierOf(tag.dimension) !== "meta" ? (
          <Link href={`/graph?tags=${encodeURIComponent(slug)}&days=365`} className="btn-ghost w-fit">
            {g("openInMap")}
            <ArrowRightIcon size={14} />
          </Link>
        ) : null}

        {tag.parent || tag.children.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5 border-t pt-3">
            {tag.parent ? (
              <>
                <span className="text-xs text-muted-foreground">{t("partOf")}</span>
                <TagChip tag={tag.parent} locale={locale} />
              </>
            ) : null}
            {tag.children.map((c) => (
              <TagChip key={c.slug} tag={c} locale={locale} showCount />
            ))}
          </div>
        ) : null}

        {coTags.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5 border-t pt-3">
            <span className="text-xs text-muted-foreground">{t("appearsWith")}</span>
            {coTags.slice(0, 8).map((c) => (
              <Link key={c.slug} href={`/tag/${c.slug}`} className="chip hover:bg-border">
                {c.labels?.[locale] || c.name}
                <span className="tag-count">{c.count}</span>
              </Link>
            ))}
          </div>
        ) : null}
      </header>

      {summary?.available && summary.summary[locale] ? (
        <section className="mt-6 border-l-2 pl-4" style={{ borderColor: tone }}>
          <h2 className="mb-1.5 text-sm text-muted-foreground">{t("whatSaid")}</h2>
          <p className="text-pretty leading-relaxed">{summary.summary[locale]}</p>
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

      <div className="archive-grid mt-8">
        {results.items.map((p) => (
          <PostCard key={p.id} post={p} locale={locale} />
        ))}
      </div>

      {results.has_more ? (
        <Link href={`/search?tags=${encodeURIComponent(slug)}`} className="btn-ghost mt-6 w-full justify-center">
          {t("seeAll", { count: tag.post_count })}
          <ArrowRightIcon size={14} />
        </Link>
      ) : null}
    </div>
  );
}
