import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { DimensionTabs } from "@/components/tags/DimensionTabs";
import { TagCloud } from "@/components/tags/TagCloud";
import { TagsFrame } from "@/components/tags/TagsFrame";
import { apiFetch } from "@/lib/api";
import { tierOf } from "@/lib/dimensions";
import { dimensionDescription, dimensionLabel, tagLabel } from "@/lib/labels";
import type { DimensionOut, TagOut } from "@/lib/types";

type Props = { params: Promise<{ dimension: string }> };

export async function generateMetadata({ params }: Props) {
  const { dimension } = await params;
  const [dimensions, locale, t] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    getLocale(),
    getTranslations("tags"),
  ]);
  const dim = dimensions.find((d) => d.key === dimension);
  return { title: dim ? dimensionLabel(dim, locale) : t("title") };
}

export default async function DimensionPage({ params }: Props) {
  const { dimension } = await params;
  const [dimensions, tags, locale, t] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    apiFetch<TagOut[]>(`/api/tags?dimension=${encodeURIComponent(dimension)}&limit=500`),
    getLocale(),
    getTranslations("tags"),
  ]);
  const dim = dimensions.find((d) => d.key === dimension);
  if (!dim) notFound();

  return (
    <div>
      <h1 className="sr-only">{t("title")}</h1>
      <TagsFrame
        title={t("title")}
        countLabel={t("count", { count: String(tags.length) })}
        description={dimensionDescription(dim, locale) ?? t("intro")}
        tags={tags.map((tag) => ({
          slug: tag.slug,
          label: tagLabel(tag, locale),
          count: tag.post_count,
          tier: tierOf(tag.dimension),
        }))}
        labels={{
          search: t("search"),
          noMatch: t("noMatch"),
          filter: t("filter"),
          groups: t("groups"),
          show: t("showControls"),
          hide: t("hideControls"),
        }}
        tabs={<DimensionTabs dimensions={dimensions} active={dim.key} locale={locale} />}
      >
        {tags.length === 0 ? <p className="tags-empty">{t("empty")}</p> : <TagCloud tags={tags} locale={locale} />}
      </TagsFrame>
    </div>
  );
}
