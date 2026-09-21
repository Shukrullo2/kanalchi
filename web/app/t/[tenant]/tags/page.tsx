import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import { dimensionLabel, tagLabel } from "@/lib/labels";
import type { DimensionOut, TagOut } from "@/lib/types";

export const metadata = { title: "Tags" };

export default async function TagsPage() {
  const [dimensions, tags, locale, t] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    apiFetch<TagOut[]>("/api/tags?limit=500"),
    getLocale(),
    getTranslations("common"),
  ]);
  const byDimension = new Map<string, TagOut[]>();
  for (const tag of tags) {
    if (!tag.dimension) continue;
    const bucket = byDimension.get(tag.dimension) ?? [];
    bucket.push(tag);
    byDimension.set(tag.dimension, bucket);
  }

  if (dimensions.length === 0) {
    return <p className="text-muted-foreground">{t("notIndexedYet")}</p>;
  }

  return (
    <div className="space-y-8">
      {dimensions.map((dim) => {
        const dimTags = (byDimension.get(dim.key) ?? []).slice(0, 24);
        if (dimTags.length === 0) return null;
        return (
          <section key={dim.key}>
            <h2 className="mb-2 flex items-baseline gap-2">
              <Link href={`/tags/${dim.key}`} className="font-medium hover:underline">
                {dimensionLabel(dim, locale)}
              </Link>
              <span className="text-xs text-muted-foreground">{dim.tag_count}</span>
            </h2>
            <div className="flex flex-wrap gap-1.5">
              {dimTags.map((tag) => (
                <Link
                  key={tag.slug}
                  href={`/tag/${tag.slug}`}
                  className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-sm hover:bg-muted"
                >
                  {tagLabel(tag, locale)}
                  <span className="text-xs text-muted-foreground">{tag.post_count}</span>
                </Link>
              ))}
              {dim.tag_count > dimTags.length ? (
                <Link href={`/tags/${dim.key}`} className="px-2 py-0.5 text-sm text-muted-foreground hover:underline">
                  +{dim.tag_count - dimTags.length}
                </Link>
              ) : null}
            </div>
          </section>
        );
      })}
    </div>
  );
}
