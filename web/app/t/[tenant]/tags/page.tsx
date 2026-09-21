import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { ArrowRightIcon } from "@/components/Icons";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch } from "@/lib/api";
import { dimensionLabel } from "@/lib/labels";
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
    byDimension.set(tag.dimension, [...(byDimension.get(tag.dimension) ?? []), tag]);
  }

  if (dimensions.length === 0) {
    return (
      <div className="card-surface p-12 text-center text-sm text-muted-foreground">{t("notIndexedYet")}</div>
    );
  }

  return (
    <div className="space-y-5">
      {dimensions.map((dim, i) => {
        const dimTags = (byDimension.get(dim.key) ?? []).slice(0, 24);
        if (dimTags.length === 0) return null;
        return (
          <section
            key={dim.key}
            className="card-surface animate-rise p-4 sm:p-5"
            style={{ animationDelay: `${Math.min(i, 8) * 30}ms` }}
          >
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2 className="flex items-baseline gap-2 font-medium">
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ background: `var(--dim-${dim.key}, var(--dim-default))` }}
                  aria-hidden
                />
                {dimensionLabel(dim, locale)}
                <span className="text-xs font-normal text-muted-foreground">{dim.tag_count}</span>
              </h2>
              {dim.tag_count > dimTags.length ? (
                <Link href={`/tags/${dim.key}`} className="link-quiet flex items-center gap-1 text-xs">
                  all <ArrowRightIcon size={12} />
                </Link>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {dimTags.map((tag) => (
                <TagChip key={tag.slug} tag={tag} locale={locale} showCount />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
