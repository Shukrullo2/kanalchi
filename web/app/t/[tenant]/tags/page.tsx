import Link from "next/link";
import { getLocale, getTranslations } from "next-intl/server";
import { TagChip } from "@/components/tags/TagChip";
import { apiFetch } from "@/lib/api";
import { tierOf } from "@/lib/dimensions";
import { dimensionLabel } from "@/lib/labels";
import type { DimensionOut, TagOut } from "@/lib/types";

export const metadata = { title: "Index" };

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
    return <div className="py-16 text-center text-sm text-muted-foreground">{t("notIndexedYet")}</div>;
  }

  return (
    <div>
      <header className="pb-6">
        <h1 className="text-[1.75rem] font-semibold tracking-tight">The index</h1>
        <p className="mt-2 max-w-[60ch] text-[0.9375rem] text-muted-foreground">
          Every post is filed under the subjects it covers and the people, bodies and places it names.
          These lists were built from the channel&rsquo;s own history, so they differ from channel to channel.
        </p>
      </header>

      <div className="divide-y border-t">
        {dimensions.map((dim) => {
          const dimTags = (byDimension.get(dim.key) ?? []).slice(0, 24);
          if (dimTags.length === 0) return null;
          return (
            <section key={dim.key} className="py-5">
              <div className="mb-3 flex items-baseline justify-between gap-3">
                <h2 className="flex items-baseline gap-2 text-[0.9375rem] font-medium">
                  {dimensionLabel(dim, locale)}
                  <span className="tnum text-xs font-normal text-muted-foreground">{dim.tag_count}</span>
                </h2>
                {dim.tag_count > dimTags.length ? (
                  <Link href={`/tags/${dim.key}`} className="link-quiet text-xs">
                    All {dim.tag_count}
                  </Link>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-1.5" data-tier={tierOf(dim.key)}>
                {dimTags.map((tag) => (
                  <TagChip key={tag.slug} tag={tag} locale={locale} showCount />
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
