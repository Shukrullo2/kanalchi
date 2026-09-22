import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { DimensionTabs } from "@/components/tags/DimensionTabs";
import { TagCard } from "@/components/tags/TagCard";
import { apiFetch } from "@/lib/api";
import { dimensionLabel } from "@/lib/labels";
import type { DimensionOut, TagOut } from "@/lib/types";

type Props = { params: Promise<{ dimension: string }> };

export async function generateMetadata({ params }: Props) {
  const { dimension } = await params;
  const [dimensions, locale] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    getLocale(),
  ]);
  const dim = dimensions.find((d) => d.key === dimension);
  return { title: dim ? dimensionLabel(dim, locale) : "Index" };
}

export default async function DimensionPage({ params }: Props) {
  const { dimension } = await params;
  const [dimensions, tags, locale, t, tc] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    apiFetch<TagOut[]>(`/api/tags?dimension=${encodeURIComponent(dimension)}&limit=500`),
    getLocale(),
    getTranslations("tags"),
    getTranslations("common"),
  ]);
  const dim = dimensions.find((d) => d.key === dimension);
  if (!dim) notFound();

  return (
    <div>
      <header className="pb-5 pt-2">
        <h1 className="text-[1.75rem] font-semibold tracking-tight sm:text-[2rem]">{t("title")}</h1>
        <p className="mt-2 max-w-[62ch] text-[0.9375rem] text-muted-foreground">
          {dim.description || t("intro")}
        </p>
      </header>

      <DimensionTabs dimensions={dimensions} active={dim.key} locale={locale} />

      {tags.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">{t("empty")}</p>
      ) : (
        <div className="tag-grid mt-5">
          {tags.map((tag) => (
            <TagCard key={tag.slug} tag={tag} locale={locale} countLabel={tc("posts", { count: tag.post_count })} />
          ))}
        </div>
      )}
    </div>
  );
}
