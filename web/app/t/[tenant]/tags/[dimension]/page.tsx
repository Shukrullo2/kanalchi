import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale } from "next-intl/server";
import { apiFetch } from "@/lib/api";
import { dimensionLabel, tagLabel } from "@/lib/labels";
import type { DimensionOut, TagOut } from "@/lib/types";

type Props = { params: Promise<{ dimension: string }> };

export default async function DimensionPage({ params }: Props) {
  const { dimension } = await params;
  const [dimensions, tags, locale] = await Promise.all([
    apiFetch<DimensionOut[]>("/api/dimensions"),
    apiFetch<TagOut[]>(`/api/tags?dimension=${encodeURIComponent(dimension)}&limit=500`),
    getLocale(),
  ]);
  const dim = dimensions.find((d) => d.key === dimension);
  if (!dim) notFound();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-medium">{dimensionLabel(dim, locale)}</h1>
        {dim.description ? <p className="text-sm text-muted-foreground">{dim.description}</p> : null}
      </div>
      <ul className="divide-y">
        {tags.map((tag) => (
          <li key={tag.slug} className="flex items-baseline justify-between gap-4 py-2">
            <Link href={`/tag/${tag.slug}`} className="hover:underline">
              {tagLabel(tag, locale)}
            </Link>
            <span className="text-sm text-muted-foreground">{tag.post_count}</span>
          </li>
        ))}
      </ul>
      <Link href="/tags" className="inline-block text-sm underline">
        ← all tags
      </Link>
    </div>
  );
}
